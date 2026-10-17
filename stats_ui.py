"""
صفحه «آمار و گزارشات».

- «امتیاز ریسک» یک محاسبه ساده است (نه یادگیری ماشین): غیبت نسبت به ریتم بسته + مرحله مصرف بسته
- فهرست پیگیری امروز: «بازگرداندن» (غیبت) و «تمدید» (تمام‌شدن بسته) با علت، متن آماده و لینک‌های تماس / پیامک / واتس‌اپ
  (برنامه چیزی نمی‌فرستد؛ فقط لینک می‌سازد و مدیر خودش «ارسال» را می‌زند)
- جدول ریسک با فیلتر، نمودارهای ساعات شلوغی / روزهای هفته / روند ۱۴ روز، بازه زمانی، دانلود فهرست پیگیری
- روز غیبت = روز تقویمی تهران (مثل صفحه داشبورد)

توابع «خالص» (بدون Streamlit) قابل تست‌اند.
"""
import csv
import html
import io
from datetime import datetime, timedelta
from urllib.parse import quote

import pandas as pd
import streamlit as st

from ai_analytics import get_subscription_checkin_counts
from checkin_ui import last_visit_text, logs_from_last, to_tehran
from db_manager import get_all_members, get_checkin_times, get_last_checkins
from panel_ui import (TEHRAN, _html, _kpi, _parse_date, build_rows, fa, jalali_numeric, jalali_text,
                      normalize_text, page_header)

# ---------------- قاعده امتیازدهی ----------------
LEVEL_HIGH_MIN = 70
LEVEL_MEDIUM_MIN = 40
POINTS_PER_MISSED_SESSION = 15.0     # هر جلسه از دست‌رفته
LIFECYCLE_MAX_POINTS = 30.0          # سهم مرحله مصرف بسته
ENDING_MAX_SESSIONS = 2              # مثل داشبورد: ≤۲ جلسه
ENDING_MAX_DAYS = 3                  # مثل داشبورد: ≤۳ روز

FOLLOWUP_MAX = 8

LEVELS = {
    "high": {"name": "بالا", "label": "ریسک بالا", "emoji": "🔴", "chip": "chip-red", "color": "#EF4444"},
    "medium": {"name": "متوسط", "label": "ریسک متوسط", "emoji": "🟡", "chip": "chip-amber", "color": "#F59E0B"},
    "low": {"name": "پایین", "label": "ریسک پایین", "emoji": "🟢", "chip": "chip-green", "color": "#10B981"},
}
CATEGORIES = {"return": "بازگرداندن", "renew": "تمدید"}
RANGE_OPTIONS = {"7": ("۷ روز اخیر", 7), "30": ("۳۰ روز اخیر", 30), "all": ("همه ترددها", None)}
WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
WEEKDAY_INITIALS = ["ش", "ی", "د", "س", "چ", "پ", "ج"]

DEFAULT_TEMPLATES = {
    "return": "سلام {نام} عزیز 🌟\nچند روزیه توی باشگاه {باشگاه} ندیدیمت و {جلسه} جلسه از بسته‌ت باقی مونده. هر وقت آماده بودی منتظرتیم 💪",
    "renew": "سلام {نام} عزیز\nبسته تمرینی‌ت توی باشگاه {باشگاه} {وضعیت}. برای تمدید با ما هماهنگ کن تا مسیر تمرینت قطع نشه 🙌",
}


# =============================================================
# امتیاز ریسک و دسته‌بندی پیگیری
# =============================================================
def risk_level(score):
    if score >= LEVEL_HIGH_MIN:
        return "high"
    if score >= LEVEL_MEDIUM_MIN:
        return "medium"
    return "low"


def score_components(total, sessions_left, days):
    """
    (جلسات از دست‌رفته، امتیاز غیبت، امتیاز مرحله بسته، امتیاز خام)
    جلسات از دست‌رفته = روز غیبت × (جلسات بسته ÷ ۳۰)  ← هر جلسه از دست‌رفته ۱۵ امتیاز
    امتیاز مرحله بسته  = ۳۰ × (سهم مصرف‌شده از بسته)²
    """
    total = total or 12
    missed = days * (total / 30.0)
    absence_points = missed * POINTS_PER_MISSED_SESSION
    progress = max(0.0, min(1.0, 1.0 - (sessions_left or 0) / total))
    lifecycle_points = LIFECYCLE_MAX_POINTS * progress ** 2
    return missed, absence_points, lifecycle_points, absence_points + lifecycle_points


def follow_up_category(sessions_left, level, absence_points, lifecycle_points, days_left):
    """«return» (بازگرداندن) | «renew» (تمدید) | None"""
    if sessions_left == 0:
        return "renew"
    if level in ("high", "medium") and absence_points >= lifecycle_points:
        return "return"
    if sessions_left <= ENDING_MAX_SESSIONS or (days_left is not None and days_left <= ENDING_MAX_DAYS):
        return "renew"
    return None


def build_risk_rows(raw_members, rows, today):
    """امتیاز ریسک اعضای دارای اشتراک فعال (روی ردیف‌های build_rows داشبورد؛ تعریف غیبت یکسان)"""
    joins = {m.get("id"): _parse_date(m.get("join_date")) for m in raw_members}
    items = []
    for r in rows:
        if r["status_key"] != "active":
            continue
        total = r["total"] or 12
        left = r["sessions_left"] or 0
        days = r["days_absent"]
        if days is None:                                   # هنوز ورودی نداشته: از تاریخ عضویت
            joined = joins.get(r["id"])
            days = max(0, (today - joined).days) if joined else 0

        missed, absence_points, lifecycle_points, raw = score_components(total, left, days)
        score = round(min(100.0, raw), 1)
        level = risk_level(score)
        days_left = r.get("days_left")

        reasons = []
        if left == 0:
            reasons.append("جلسات بسته تمام شده")
        elif left <= ENDING_MAX_SESSIONS:
            reasons.append(f"فقط {fa(left)} جلسه مانده")
        if days_left is not None and 0 <= days_left <= ENDING_MAX_DAYS:
            reasons.append("امروز آخرین روز اشتراک است" if days_left == 0 else f"{fa(days_left)} روز تا پایان اشتراک")
        if missed >= 1 and days > 0:
            if r["days_absent"] is None:
                reasons.append(f"هنوز ورود نداشته ({fa(days)} روز از عضویت)")
            else:
                reasons.append(f"{fa(days)} روز غیبت (حدود {fa(round(missed))} جلسه از دست رفته)")

        items.append({
            "id": r["id"], "name": r["name"], "phone": r["phone"], "national_id": r["national_id"],
            "score": score, "raw_score": raw, "level": level, "days": days, "days_absent": r["days_absent"],
            "sessions_left": left, "total": total, "days_left": days_left, "end_date": r["end_date"],
            "missed": missed, "absence_points": absence_points, "lifecycle_points": lifecycle_points,
            "reasons": reasons,
            "category": follow_up_category(left, level, absence_points, lifecycle_points, days_left),
        })
    items.sort(key=lambda x: (-x["score"], -x["raw_score"], -x["days"]))      # هم‌امتیازهای سقف ۱۰۰ با امتیاز خام جدا می‌شوند
    return items


def followup_items(items, category="all"):
    """فهرست پیگیری: اول «بازگرداندن» (بر اساس امتیاز)، بعد «تمدید» (اول جلسه تمام‌شده‌ها، بعد نزدیک‌ترین انقضا)"""
    returns = [i for i in items if i["category"] == "return"]
    renews = sorted((i for i in items if i["category"] == "renew"),
                    key=lambda x: (x["sessions_left"], x["days_left"] if x["days_left"] is not None else 99, -x["score"]))
    if category == "return":
        return returns
    if category == "renew":
        return renews
    return returns + renews


def risk_counts(items):
    counts = {"all": len(items), "high": 0, "medium": 0, "low": 0}
    for i in items:
        counts[i["level"]] += 1
    return counts


def filter_risk_items(items, level, query):
    out = [i for i in items if level in (None, "all") or i["level"] == level]
    q = normalize_text(query)
    if q:
        out = [i for i in out if q in normalize_text(i["name"]) or q in normalize_text(i["phone"]) or q in normalize_text(i["id"])]
    return out


# =============================================================
# پیام و لینک‌ها (بدون هیچ اتصال خارجی)
# =============================================================
def render_message(template, item, club):
    first = (item["name"] or "").split()[0] if item["name"] else ""
    status = "تموم شده" if item["sessions_left"] == 0 else "داره تموم می‌شه"
    return (template.replace("{نام}", first).replace("{باشگاه}", str(club)).replace("{جلسه}", fa(item["sessions_left"]))
            .replace("{وضعیت}", status).replace("{غیبت}", fa(item["days"])))


def valid_phone(phone):
    p = str(phone or "")
    return len(p) == 11 and p.startswith("09") and p.isdigit()


def whatsapp_number(phone):
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if digits.startswith("0"):
        return "98" + digits[1:]
    return digits


def contact_links(phone, message):
    """لینک‌های تماس / پیامک / واتس‌اپ؛ برای شماره نامعتبر None"""
    if not valid_phone(phone):
        return None
    text = quote(message, safe="")
    return {
        "call": f"tel:{phone}",
        "sms": f"sms:{phone}?body={text}",
        "whatsapp": f"https://wa.me/{whatsapp_number(phone)}?text={text}",
    }


def followup_csv(items, today):
    """CSV مناسب Excel (UTF-8 با BOM تا حروف فارسی درست نمایش داده شود)"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["نام و نام خانوادگی", "شماره تماس", "دسته پیگیری", "سطح ریسک", "امتیاز", "علت",
                     "روز غیبت", "جلسات باقی‌مانده", "تاریخ انقضا"])
    for i in items:
        writer.writerow([
            i["name"], i["phone"], CATEGORIES.get(i["category"], ""), LEVELS[i["level"]]["name"], i["score"],
            " | ".join(i["reasons"]), "" if i["days_absent"] is None else i["days_absent"],
            f'{i["sessions_left"]} از {i["total"]}', jalali_numeric(i["end_date"]) if i["end_date"] else "",
        ])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


# =============================================================
# آمار ترددها
# =============================================================
def weekday_index(d):
    """۰ = شنبه ... ۶ = جمعه"""
    return (d.weekday() + 2) % 7


def peak_window(hourly):
    """شلوغ‌ترین بازه دو ساعته: (ساعت شروع، ساعت پایان، تعداد) یا None"""
    best = None
    for h in range(23):
        s = hourly[h] + hourly[h + 1]
        if best is None or s > best[2]:
            best = (h, h + 2, s)
    return best if best and best[2] > 0 else None


def quiet_hours(hourly):
    """کم‌تردد‌ترین ساعت‌ها (همه ساعت‌هایی که کمترین تعداد را دارند) در بازه‌ای که ورود داشته"""
    active = [h for h, c in enumerate(hourly) if c > 0]
    if len(active) < 2:
        return []
    span = range(min(active), max(active) + 1)
    lowest = min(hourly[h] for h in span)
    if lowest == max(hourly[h] for h in span):
        return []
    return [h for h in span if hourly[h] == lowest]


def hour_ranges_text(hours, max_ranges=3):
    """ساعت‌های پیوسته را فشرده می‌کند: [9,10,11,12,18] ← «۹ تا ۱۲ و ۱۸»"""
    if not hours:
        return ""
    groups, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h == prev + 1:
            prev = h
            continue
        groups.append((start, prev))
        start = prev = h
    groups.append((start, prev))
    parts = [fa(a) if a == b else f"{fa(a)} تا {fa(b)}" for a, b in groups[:max_ranges]]
    return " و ".join(parts) + (" و ..." if len(groups) > max_ranges else "")


def checkin_stats(times, today, range_days):
    local = []
    for t in times:
        try:
            local.append(to_tehran(t))
        except Exception:
            continue
    start = None if range_days is None else today - timedelta(days=range_days - 1)
    in_range = [t for t in local if start is None or t.date() >= start]

    hourly, weekday = [0] * 24, [0] * 7
    for t in in_range:
        hourly[t.hour] += 1
        weekday[weekday_index(t.date())] += 1

    days14 = [today - timedelta(days=i) for i in range(13, -1, -1)]          # قدیم ← جدید
    counts = {d: 0 for d in days14}
    for t in local:
        if t.date() in counts:
            counts[t.date()] += 1
    daily = [(d, counts[d]) for d in days14]
    return {
        "total": len(in_range), "hourly": hourly, "weekday": weekday, "daily": daily,
        "last7": sum(c for _, c in daily[7:]), "prev7": sum(c for _, c in daily[:7]),
        "peak": peak_window(hourly), "quiet": quiet_hours(hourly),
    }


def trend_text(last7, prev7):
    if prev7 == 0:
        return f"۷ روز اخیر {fa(last7)} ورود ثبت شده (۷ روز قبل از آن ورودی ثبت نشده)."
    change = round((last7 - prev7) * 100 / prev7)
    if change == 0:
        word = "بدون تغییر نسبت به ۷ روز قبل"
    else:
        word = f'{"رشد" if change > 0 else "کاهش"} {fa(abs(change))}٪ نسبت به ۷ روز قبل ({fa(prev7)} ورود)'
    return f"۷ روز اخیر {fa(last7)} ورود؛ {word}."


# =============================================================
# HTML
# =============================================================
def _chip(css, text):
    return f'<span class="chip {css}">{html.escape(str(text))}</span>'


def section_title(title, sub=""):
    sub_html = f'<div class="sec-sub">{sub}</div>' if sub else ""
    return _html('<div class="sec-head">', f'<div class="sec-title">{title}</div>', sub_html, "</div>")


def bar_chart_html(values, labels, titles, highlight=(), height=190):
    """نمودار میله‌ای HTML/CSS (راست‌به‌چپ، بدون وابستگی به کتابخانه نمودار)"""
    mx = max(values) if values else 0
    cols = []
    for i, v in enumerate(values):
        pct = 0 if mx == 0 else round(v * 100 / mx)
        cls = "bar-fill bar-hi" if i in highlight else "bar-fill"
        val = f'<span class="bar-val">{fa(v)}</span>' if v else '<span class="bar-val">&nbsp;</span>'
        cols.append(
            f'<div class="bar-col" title="{html.escape(titles[i])}">{val}'
            f'<div class="bar-track"><div class="{cls}" style="height:{pct}%"></div></div>'
            f'<span class="bar-label">{labels[i]}</span></div>'
        )
    return f'<div class="bars" style="height:{height}px">{"".join(cols)}</div>'


def hourly_chart_html(hourly, peak):
    active = [h for h, c in enumerate(hourly) if c > 0]
    if not active:
        return '<div class="ci-empty">در این بازه هنوز ورودی ثبت نشده است.</div>'
    start, end = min(6, min(active)), max(23, max(active))
    hours = list(range(start, end + 1))
    hi = {i for i, h in enumerate(hours) if peak and peak[0] <= h < peak[1]}
    return bar_chart_html([hourly[h] for h in hours], [fa(h) for h in hours],
                          [f"ساعت {fa(h)}: {fa(hourly[h])} ورود" for h in hours], hi)


def hourly_summary(stats):
    parts = []
    if stats["peak"]:
        a, b, n = stats["peak"]
        pct = round(n * 100 / stats["total"]) if stats["total"] else 0
        parts.append(f"شلوغ‌ترین بازه: <b>{fa(a)} تا {fa(b)}</b> ({fa(n)} ورود، {fa(pct)}٪ ورودها)")
    quiet = stats["quiet"]
    if quiet:
        label = "ساعت‌های بدون ورود" if stats["hourly"][quiet[0]] == 0 else "کم‌تردد‌ترین ساعت‌ها"
        parts.append(f"{label}: {hour_ranges_text(quiet)}")
    return " · ".join(parts)


def weekday_chart_html(weekday):
    if sum(weekday) == 0:
        return '<div class="ci-empty">در این بازه هنوز ورودی ثبت نشده است.</div>'
    top = weekday.index(max(weekday))
    return bar_chart_html(weekday, WEEKDAY_INITIALS, [f"{WEEKDAYS[i]}: {fa(c)} ورود" for i, c in enumerate(weekday)], {top}, height=150)


def trend_chart_html(daily):
    if sum(c for _, c in daily) == 0:
        return '<div class="ci-empty">در ۱۴ روز اخیر ورودی ثبت نشده است.</div>'
    labels = [fa(jalali_numeric(d).split("/")[2]) for d, _ in daily]
    titles = [f"{jalali_text(d)}: {fa(c)} ورود" for d, c in daily]
    return bar_chart_html([c for _, c in daily], labels, titles, {len(daily) - 1}, height=150)


def risk_bar_html(counts):
    total = counts["all"]
    if total == 0:
        return ""
    order = ["low", "medium", "high"]
    segs = "".join(f'<div class="rk-seg" style="width:{counts[k] * 100 / total:.2f}%;background:{LEVELS[k]["color"]}"></div>'
                   for k in order if counts[k])
    legend = "".join(
        f'<span class="rk-leg"><i class="kpi-dot" style="background:{LEVELS[k]["color"]}"></i>{LEVELS[k]["label"]} · {fa(counts[k])} نفر '
        f'({fa(round(counts[k] * 100 / total))}٪)</span>' for k in order)
    return _html('<div class="rk-card">',
                 f'<div class="rk-title">توزیع ریسک اعضا <span class="rk-sub">بین {fa(total)} عضو دارای اشتراک فعال</span></div>',
                 f'<div class="rk-bar">{segs}</div>', f'<div class="rk-legend">{legend}</div>', "</div>")


def followup_card_html(item, message):
    lv = LEVELS[item["level"]]
    links = contact_links(item["phone"], message)
    if links:
        actions = (f'<a class="act" href="{html.escape(links["call"])}">تماس</a>'
                   f'<a class="act" href="{html.escape(links["sms"])}">پیامک</a>'
                   f'<a class="act act-wa" href="{html.escape(links["whatsapp"])}" target="_blank" rel="noopener noreferrer">واتس‌اپ</a>')
    else:
        actions = '<span class="fu-nophone">شماره معتبر ثبت نشده است</span>'
    reasons = "".join(_chip("chip-gray", r) for r in item["reasons"]) or _chip("chip-gray", "بدون علت خاص")
    msg_html = html.escape(message).replace("\n", "<br>")
    level_chip = _chip(lv["chip"], lv["label"] + " · " + fa(round(item["score"])))     # (بدون f-string تو در تو؛ سازگار با پایتون‌های قدیمی‌تر)
    return _html(
        '<div class="fu-card">',
        f'<div class="fu-top"><span class="ci-name">{html.escape(str(item["name"]))}</span>{level_chip}</div>',
        f'<div class="ci-meta">{html.escape(str(item["phone"] or ""))} · کد {fa(item["id"])} · آخرین ورود: {last_visit_text(item["days_absent"])}</div>',
        f'<div class="ci-chips">{reasons}</div>',
        f'<div class="fu-actions">{actions}</div>',
        f'<details class="fu-msg"><summary>متن پیام</summary><div>{msg_html}</div></details>',
        "</div>",
    )


EXPLAIN_HTML = _html(
    '<div class="explain">',
    '<div class="guide-step"><span>این یک <b>محاسبه ساده</b> است (نه یادگیری ماشین) و فقط از سه چیز استفاده می‌کند: <b>غیبت، جلسات باقی‌مانده و نوع بسته</b>.</span></div>',
    '<div class="guide-step"><span class="guide-num">۱</span><span><b>جلسات از دست‌رفته:</b> روزهای غیبت × (تعداد جلسات بسته ÷ ۳۰). عضو بسته ۱۲ جلسه‌ای را تقریباً هر ۲٫۵ روز و عضو بسته ۲۴ جلسه‌ای را تقریباً هر ۱٫۲۵ روز یک‌بار انتظار داریم. هر جلسه از دست‌رفته <b>۱۵ امتیاز</b>.</span></div>',
    '<div class="guide-step"><span class="guide-num">۲</span><span><b>مرحله بسته:</b> هرچه بیشتر از بسته مصرف شده باشد، تا <b>۳۰ امتیاز</b> (نزدیک پایان بسته سریع‌تر زیاد می‌شود، چون وقت تصمیم تمدید است).</span></div>',
    '<div class="guide-step"><span class="guide-num">۳</span><span><b>جمع با سقف ۱۰۰:</b> ۷۰ به بالا «بالا»، ۴۰ به بالا «متوسط»، کمتر از ۴۰ «پایین».</span></div>',
    '<div class="guide-note">مثال: عضو بسته ۲۴ جلسه‌ای با ۷ روز غیبت حدود ۵٫۶ جلسه از دست داده (۸۴ امتیاز) و «بالا» می‌شود؛ ولی عضو بسته ۱۲ جلسه‌ای با همان ۷ روز غیبت حدود ۲٫۸ جلسه از دست داده (۴۲ امتیاز) و «متوسط» است.</div>',
    '<div class="guide-note">در فهرست پیگیری: «<b>بازگرداندن</b>» برای کسانی است که جلسه دارند ولی غیبت امتیازشان را بالا برده؛ «<b>تمدید</b>» برای کسانی است که جلساتشان تمام شده یا به‌زودی تمام می‌شود (۲ جلسه یا ۳ روز).</div>',
    '</div>',
)


# =============================================================
# صفحه
# =============================================================
def _selected(value, options, default):
    return value if value in options else default


def render_stats(club_id):
    today = datetime.now(TEHRAN).date()

    members = get_all_members(club_id)
    rows = build_rows(members, logs_from_last(get_last_checkins(club_id)), get_subscription_checkin_counts(club_id), today)
    items = build_risk_rows(members, rows, today)
    counts = risk_counts(items)

    st.markdown(
        page_header("آمار و تحلیل باشگاه",
                    f"امروز {jalali_text(today)} · امتیاز ریسک بر پایه غیبت، جلسات باقی‌مانده و نوع بسته محاسبه می‌شود"),
        unsafe_allow_html=True,
    )

    # ---------- بازه زمانی ترددها ----------
    range_key = _selected(
        st.segmented_control("بازه تحلیل ترددها", options=list(RANGE_OPTIONS), format_func=lambda k: RANGE_OPTIONS[k][0],
                             default="all", key="st_range", label_visibility="collapsed"),
        RANGE_OPTIONS, "all")
    range_label, range_days = RANGE_OPTIONS[range_key]
    stats = checkin_stats(get_checkin_times(club_id), today, range_days)

    # ---------- کارت‌های خلاصه ----------
    follow_all = followup_items(items)
    n_return = sum(1 for i in follow_all if i["category"] == "return")
    n_renew = len(follow_all) - n_return
    peak = stats["peak"]
    st.markdown(_html(
        '<div class="kpi-grid">',
        _kpi("اعضای دارای اشتراک فعال", len(items), f"از {fa(len(rows))} عضو", "#38BDF8"),
        _kpi("نیازمند پیگیری", len(follow_all), f"{fa(n_return)} بازگرداندن · {fa(n_renew)} تمدید", "#F59E0B"),
        _kpi("ورودها", stats["total"], range_label, "#10B981"),
        _kpi("شلوغ‌ترین بازه", f"{peak[0]} تا {peak[1]}" if peak else "—", f"{fa(peak[2])} ورود" if peak else "هنوز ورودی نیست", "#A78BFA"),
        "</div>",
    ), unsafe_allow_html=True)

    # ---------- توزیع ریسک ----------
    st.markdown(risk_bar_html(counts), unsafe_allow_html=True)
    with st.expander("امتیاز چطور حساب می‌شود؟"):
        st.markdown(EXPLAIN_HTML, unsafe_allow_html=True)

    if not items:
        st.info("هنوز عضوی با اشتراک فعال نیست؛ بعد از ثبت عضو و تخصیص بسته، تحلیل ریسک اینجا نمایش داده می‌شود.")

    # ---------- فهرست پیگیری ----------
    st.markdown(section_title("پیگیری امروز", "اعضایی که الان بیشترین نیاز به تماس دارند؛ با یک ضربه تماس بگیرید یا پیام آماده را باز کنید"),
                unsafe_allow_html=True)
    if follow_all:
        cat_opts = ["all", "return", "renew"]
        cat_counts = {"all": len(follow_all), "return": n_return, "renew": n_renew}
        cat_names = {"all": "همه", "return": "بازگرداندن", "renew": "تمدید"}
        cat = _selected(
            st.segmented_control("دسته پیگیری", options=cat_opts, format_func=lambda k: f"{cat_names[k]} ({fa(cat_counts[k])})",
                                 default="all", key="st_fu_cat", label_visibility="collapsed"),
            cat_opts, "all")

        with st.expander("ویرایش متن پیام‌ها"):
            st.caption("جای‌نگهدارها: {نام} ، {باشگاه} ، {جلسه} ، {وضعیت} ، {غیبت}. تغییرات تا بستن مرورگر حفظ می‌شود.")
            tpl_return = st.text_area("پیام «بازگرداندن»", value=st.session_state.get("st_tpl_return", DEFAULT_TEMPLATES["return"]),
                                      key="st_tpl_return_w", height=110)
            tpl_renew = st.text_area("پیام «تمدید»", value=st.session_state.get("st_tpl_renew", DEFAULT_TEMPLATES["renew"]),
                                     key="st_tpl_renew_w", height=110)
            st.session_state.st_tpl_return, st.session_state.st_tpl_renew = tpl_return, tpl_renew
        templates = {"return": st.session_state.get("st_tpl_return", DEFAULT_TEMPLATES["return"]),
                     "renew": st.session_state.get("st_tpl_renew", DEFAULT_TEMPLATES["renew"])}

        shown = followup_items(items, cat)
        cards = [followup_card_html(i, render_message(templates[i["category"]], i, club_id)) for i in shown[:FOLLOWUP_MAX]]
        st.markdown(f'<div class="fu-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
        st.caption("روی گوشی هر سه دکمه کار می‌کنند؛ روی کامپیوتر معمولاً فقط واتس‌اپ. برنامه چیزی ارسال نمی‌کند؛ فقط پیام را آماده می‌کند.")
        if len(shown) > FOLLOWUP_MAX:
            st.caption(f"{fa(len(shown) - FOLLOWUP_MAX)} مورد دیگر هم هست؛ فهرست کامل را دانلود کنید یا در جدول پایین ببینید.")
        st.download_button("دانلود فهرست پیگیری (Excel)", data=followup_csv(follow_all, today),
                           file_name=f"followup_{today.isoformat()}.csv", mime="text/csv", key="st_download")
    else:
        st.markdown('<div class="ci-empty">فعلاً کسی نیاز به پیگیری ندارد. 👌</div>', unsafe_allow_html=True)

    # ---------- جدول ریسک ----------
    if items:
        st.markdown(section_title("جدول ریسک اعضا", "همه اعضای دارای اشتراک فعال، از پرریسک‌ترین به کم‌ریسک‌ترین"), unsafe_allow_html=True)
        lvl_opts = ["all", "high", "medium", "low"]
        lvl_names = {"all": "همه", "high": "بالا", "medium": "متوسط", "low": "پایین"}
        level = _selected(
            st.segmented_control("سطح ریسک", options=lvl_opts, format_func=lambda k: f"{lvl_names[k]} ({fa(counts[k])})",
                                 default="all", key="st_level", label_visibility="collapsed"),
            lvl_opts, "all")
        query = st.text_input("جستجو", placeholder="جستجوی عضو با نام، شماره تماس یا کد عضویت…", key="st_search",
                              label_visibility="collapsed")
        table_items = filter_risk_items(items, level, query)
        st.markdown(f'<div class="result-count">{fa(len(table_items))} عضو نمایش داده می‌شود</div>', unsafe_allow_html=True)
        if table_items:
            st.dataframe(
                risk_dataframe(table_items), hide_index=True, use_container_width=True,
                column_order=list(reversed(RISK_COLUMNS_RTL)),
                column_config={
                    "کد عضویت": st.column_config.NumberColumn("کد عضویت", format="%d", width="small"),
                    "امتیاز": st.column_config.ProgressColumn("امتیاز", min_value=0, max_value=100, format="%.0f", width="small"),
                    "سطح ریسک": st.column_config.TextColumn("سطح ریسک", width="small"),
                    "روز غیبت": st.column_config.TextColumn("روز غیبت", width="small"),
                    "جلسات باقی‌مانده": st.column_config.TextColumn("جلسات باقی‌مانده", width="small"),
                    "علت": st.column_config.TextColumn("علت", width="large"),
                },
            )
        else:
            st.info("هیچ عضوی با این مشخصات پیدا نشد.")

    # ---------- نمودارها ----------
    st.markdown(section_title("تحلیل ترددها", f"بازه: {range_label}"), unsafe_allow_html=True)
    st.markdown(_html('<div class="chart-card"><div class="chart-title">ساعات شلوغی باشگاه</div>',
                      hourly_chart_html(stats["hourly"], stats["peak"]),
                      f'<div class="chart-note">{hourly_summary(stats)}</div></div>'), unsafe_allow_html=True)
    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        top_day = WEEKDAYS[stats["weekday"].index(max(stats["weekday"]))] if sum(stats["weekday"]) else ""
        st.markdown(_html('<div class="chart-card"><div class="chart-title">روزهای هفته</div>',
                          weekday_chart_html(stats["weekday"]),
                          f'<div class="chart-note">{("شلوغ‌ترین روز: <b>" + top_day + "</b>") if top_day else ""}</div></div>'),
                    unsafe_allow_html=True)
    with col_b:
        st.markdown(_html('<div class="chart-card"><div class="chart-title">روند ۱۴ روز اخیر</div>',
                          trend_chart_html(stats["daily"]),
                          f'<div class="chart-note">{trend_text(stats["last7"], stats["prev7"])}</div></div>'),
                    unsafe_allow_html=True)
    st.caption("تحلیل ریسک به بازه انتخاب‌شده وابسته نیست؛ روند ۱۴ روز اخیر هم همیشه ثابت است.")


RISK_COLUMNS_RTL = ["نام و نام خانوادگی", "سطح ریسک", "امتیاز", "علت", "روز غیبت", "جلسات باقی‌مانده", "شماره تماس", "کد عضویت"]


def risk_dataframe(items):
    """
    ایموجی همیشه آخر متن می‌آید و متن‌ها با حرف/رقم فارسی شروع می‌شوند، تا جدول سلول‌ها را راست‌چین کند
    (موتور جدول جهت را از اولین کاراکتر جهت‌دار تعیین می‌کند).
    """
    def absent(i):
        return "بدون ورود" if i["days_absent"] is None else f'{fa(i["days_absent"])} روز'

    return pd.DataFrame([{
        "کد عضویت": i["id"],
        "نام و نام خانوادگی": i["name"],
        "شماره تماس": i["phone"],
        "سطح ریسک": f'{LEVELS[i["level"]]["name"]} {LEVELS[i["level"]]["emoji"]}',
        "امتیاز": float(i["score"]),
        "علت": "، ".join(i["reasons"]) or "بدون علت خاص",
        "روز غیبت": absent(i),
        "جلسات باقی‌مانده": fa(f'{i["sessions_left"]} از {i["total"]}'),
    } for i in items])
