"""
صفحه «مدیریت و حذف».

سه بخش (با کلید segmented_control، همان سبک صفحه داشبورد):
  ۱. اعضا        : جستجو + کارت عضو با سه عمل: «ابطال اشتراک»، «آرشیو»، «حذف دائمی»
                    فیلتر «غیرفعال» برای پاکسازی گروهی (آرشیو همه یک‌جا)
  ۲. آرشیو       : اعضای آرشیوشده؛ «بازگردانی» یا «حذف دائمی»
  ۳. پاکسازی کامل: پاک‌کردن همه داده‌های باشگاه، با نسخه پشتیبان (ZIP) و تایپ عبارت RESET

اصول:
- هر عضو یک «قاب» دارد که کارت اطلاعات، دکمه‌های همان عضو و کارت تأیید را با هم نگه می‌دارد؛ پس همیشه معلوم است
  دکمه مال کدام عضو است.
- هر عمل تخریبی اول یک کارت تأیید همان‌جا داخل قاب عضو نشان می‌دهد که دقیقاً چه چیزی از بین می‌رود.
- «آرشیو» عضو را از فهرست‌ها و آمار فعال کنار می‌گذارد ولی اشتراک‌ها و ترددهایش (و آمار ساعات شلوغی) حفظ می‌شود.
- ابطال اشتراک و آرشیو، تا وقتی کارت نتیجه روی صفحه است، با یک کلیک قابل برگشت‌اند.
- اگر ستون members.archived_at در دیتابیس نباشد (SQL مهاجرت اجرا نشده)، صفحه کار می‌کند و فقط آرشیو غیرفعال است.

توابع «خالص» (enrich_rows / apply_filters / pending_view / backup_zip ...) بدون Streamlit قابل تست‌اند.
"""
import html
import io
import zipfile
from datetime import datetime

import pandas as pd
import streamlit as st

from ai_analytics import get_subscription_checkin_counts, predict_churn_risk
from checkin_ui import UNDO_WINDOW_MINUTES, _columns, is_undoable, last_visit_text, logs_from_last, to_tehran
from db_manager import (archive_members, archive_supported, cancel_subscription, delete_members_permanently,
                        export_club_backup, get_all_members, get_archived_members, get_club_counts,
                        get_last_checkins, get_members_impact, measure_db_speed, reset_club_data, restore_members,
                        restore_subscription)
from member_ui import _button, _warn_card
from panel_ui import (TEHRAN, _html, _parse_date, build_rows, fa, filter_rows, jalali_text, normalize_text,
                      page_header)

PAGE_SIZE = 8            # تعداد کارت‌های نمایش‌داده‌شده در هر بار
INACTIVE_DAYS = 60       # «غیرفعال» = بدون اشتراک فعال و بدون تردد حداقل این تعداد روز
RESET_PHRASE = "RESET"   # عبارت تأیید پاکسازی کامل

SECTION_KEYS = ["members", "archive", "danger"]


# =============================================================
# ابزارهای خالص (بدون Streamlit)
# =============================================================
def is_inactive(row, days=INACTIVE_DAYS):
    """
    عضو «غیرفعال» (قابل پاکسازی): اشتراک فعال ندارد و حداقل `days` روز است که تردد نداشته؛
    اگر هیچ‌وقت تردد نداشته، از تاریخ عضویتش حساب می‌شود. اعضای دارای اشتراک فعال هرگز غیرفعال حساب نمی‌شوند.
    """
    if row["status_key"] == "active":
        return False
    if row["days_absent"] is not None:
        return row["days_absent"] >= days
    joined = row.get("joined_days")
    return joined is not None and joined >= days


def enrich_rows(rows, members, today):
    """به هر ردیف build_rows دو کلید joined_days (روز از عضویت) و inactive (قابل پاکسازی؟) اضافه می‌کند"""
    join_map = {m.get("id"): _parse_date(m.get("join_date")) for m in members}
    for r in rows:
        joined = join_map.get(r["id"])
        r["joined_days"] = (today - joined).days if joined else None
        r["inactive"] = is_inactive(r)
    return rows


# فیلترهای سریع: کلید ← (عنوان، شرط)
QUICK = {
    "all": ("همه", lambda r: True),
    "none": ("بدون اشتراک", lambda r: r["status_key"] == "none"),
    "expired": ("منقضی", lambda r: r["status_key"] == "expired"),
    "inactive": (f"غیرفعال {fa(INACTIVE_DAYS)} روزه", lambda r: r["inactive"]),
}


def count_quick(rows):
    return {key: sum(1 for r in rows if pred(r)) for key, (_, pred) in QUICK.items()}


def apply_filters(rows, quick, query):
    """اول جستجوی متنی (نام، تلفن، کد ملی، کد عضویت)، بعد فیلتر سریع"""
    pred = QUICK.get(quick or "all", QUICK["all"])[1]
    return [r for r in filter_rows(rows, "all", query) if pred(r)]


def filter_archived(items, query):
    """جستجو بین اعضای آرشیوشده"""
    q = normalize_text(query)
    if not q:
        return list(items)
    return [
        i for i in items
        if q in normalize_text(i["name"]) or q in normalize_text(i["national_id"])
        or q in normalize_text(i["phone"]) or q in normalize_text(i["id"])
    ]


def impact_phrase(impact):
    """«۳ اشتراک و ۱۲ تردد»؛ اگر تعداد معلوم نباشد، عبارت کلی"""
    impact = impact or {}
    subs, checks = impact.get("subscriptions"), impact.get("checkins")
    if subs is None or checks is None:
        return "اشتراک‌ها و ترددها"
    return f"{fa(subs)} اشتراک و {fa(checks)} تردد"


def pending_view(p):
    """
    متن کارت تأیید برای یک عملیات در انتظار.
    خروجی: {"tone": "warn"|"err", "title", "text", "confirm", "danger"} (متن خام؛ هنگام نمایش escape می‌شود)
    """
    kind, names, n = p["kind"], p["names"], len(p["ids"])
    one = n == 1
    who = f"«{names[0]}»" if one else f"{fa(n)} عضو"
    impact = impact_phrase(p.get("impact"))

    if kind in ("archive", "bulk_archive"):
        sample = ""
        if not one:
            sample = " (" + "، ".join(names[:5]) + ("، ..." if n > 5 else "") + ")"
        pron = "او" if one else "آن‌ها"
        verb = "برمی‌گردد" if one else "برمی‌گردند"
        move = "کنار می‌رود" if one else "کنار می‌روند"
        return {
            "tone": "warn",
            "title": f"آرشیو {who}؟",
            "text": (f"{who}{sample} از فهرست‌ها و آمار فعال {move}. سابقه {pron} ({impact}) حفظ می‌شود "
                     f"و هر وقت بخواهید از بخش «آرشیو» {verb}."),
            "confirm": "بله، آرشیو شود" if one else f"بله، {fa(n)} عضو آرشیو شوند",
            "danger": False,
        }
    if kind == "delete":
        extra = " اگر فقط می‌خواهید از فهرست‌ها کنار برود، به‌جای حذف «آرشیو» را بزنید." if p.get("can_archive") else ""
        return {
            "tone": "err",
            "title": f"حذف دائمی {who}؟",
            "text": f"{who} همراه با {impact} برای همیشه پاک می‌شود و قابل بازگشت نیست.{extra}",
            "confirm": "بله، برای همیشه حذف شود",
            "danger": True,
        }
    if kind == "cancel_sub":
        left = (p.get("extra") or {}).get("sessions_left", 0)
        return {
            "tone": "warn",
            "title": f"ابطال اشتراک {who}؟",
            "text": (f"اشتراک فعال منقضی می‌شود و {fa(left)} جلسه باقی‌مانده از بین می‌رود. ترددهای قبلی حفظ می‌شود. "
                     f"تا {fa(UNDO_WINDOW_MINUTES)} دقیقه می‌توانید ابطال را لغو کنید."),
            "confirm": "بله، اشتراک ابطال شود",
            "danger": False,
        }
    raise ValueError(f"unknown pending kind: {kind}")


CHURN_COLUMNS = ["analytics_id", "member_id", "churn_risk_score", "last_calculated", "club_id",
                 "full_name", "package", "risk_level", "days_since_last_checkin", "remaining_sessions"]


def risk_label(score):
    """سطح ریسک با همان آستانه‌های صفحه «آمار و گزارشات» (۷۰ و ۴۰)"""
    return "بالا" if score >= 70 else "متوسط" if score >= 40 else "پایین"


def package_name(sessions):
    """«12 جلسه‌ای» / «24 جلسه‌ای» (اگر نوع بسته معلوم نباشد «نامشخص»)"""
    try:
        if sessions is None or pd.isna(sessions):
            return "نامشخص"
        return f"{int(sessions)} جلسه‌ای"
    except (TypeError, ValueError):
        return "نامشخص"


def churn_table(df, club_id, now):
    """
    تحلیل ریسک ریزش به‌شکل جدول: ۵ ستون اول همان ستون‌های جدول ai_analytics است و ۵ ستون بعدی برای خواندن راحت‌تر
    (نام، نوع بسته ۱۲ یا ۲۴ جلسه‌ای، سطح ریسک، روز غیبت، جلسه باقی‌مانده).
    برنامه این امتیازها را در دیتابیس ذخیره نمی‌کند و هر بار از روی سوابق تردد محاسبه می‌کند؛
    پس این جدول «عکس لحظه پشتیبان‌گیری» است و فقط اعضای دارای اشتراک فعال را شامل می‌شود (پرریسک‌ترین‌ها اول).
    خروجی: (ستون‌ها, ردیف‌ها) یا None اگر چیزی برای تحلیل نباشد.
    """
    if df is None or len(df) == 0 or "churn_risk_score" not in df.columns:
        return None
    stamp = now.isoformat(timespec="seconds")
    rows = []
    for i, (_, r) in enumerate(df.sort_values("churn_risk_score", ascending=False).iterrows(), start=1):
        score = round(float(r["churn_risk_score"]), 1)
        days = r.get("days_since_last_checkin", 0)
        left = r.get("subscription_days", 0)
        rows.append((i, r["id"], score, stamp, club_id, r.get("name", ""), package_name(r.get("package_sessions")),
                     risk_label(score), 0 if pd.isna(days) else int(days), 0 if pd.isna(left) else int(left)))
    return CHURN_COLUMNS, rows


def backup_zip(tables):
    """
    tables: {نام جدول: (ستون‌ها, ردیف‌ها)} ← بایت‌های یک فایل ZIP شامل یک CSV برای هر جدول
    (UTF-8 همراه BOM تا Excel حروف فارسی را درست نشان دهد). جدول‌های خالی (مثل ai_analytics ذخیره‌شده در دیتابیس) در فایل نمی‌آیند.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, (columns, rows) in tables.items():
            if not rows:
                continue
            frame = pd.DataFrame(rows, columns=columns)
            zf.writestr(f"{name}.csv", ("\ufeff" + frame.to_csv(index=False)).encode("utf-8"))
    return buf.getvalue()


def speed_verdict(result):
    """
    نتیجه measure_db_speed را به یک جمله فارسی ساده تبدیل می‌کند: (سطح: ok|warn, متن)
    هر کلیک در برنامه حدود ۴ query می‌زند؛ پس زمان تقریبی صفحه ≈ ۴ × زمان رفت‌وبرگشت.
    """
    rt, nc = result["roundtrip_ms"], result["new_connection_ms"]
    page = rt * 4 / 1000
    if rt >= 250:
        return "warn", (f"هر query حدود {fa(round(rt))} میلی‌ثانیه طول می‌کشد (حدود {fa(round(page, 1))} ثانیه برای هر کلیک). "
                        "یعنی فاصله سرور برنامه تا دیتابیس زیاد است؛ منطقه (Region) پروژه Supabase را بررسی کنید.")
    if nc >= 700:
        return "ok", (f"ساخت اتصال تازه {fa(round(nc))} میلی‌ثانیه طول می‌کشد، ولی هر query روی اتصال آماده فقط "
                      f"{fa(round(rt))} میلی‌ثانیه است. استخر اتصال دقیقاً همین هزینه را حذف می‌کند؛ هر کلیک باید زیر "
                      f"{fa(max(1, round(page + 0.5)))} ثانیه باشد.")
    return "ok", f"اتصال سالم است: هر query حدود {fa(round(rt))} میلی‌ثانیه."


# =============================================================
# HTML
# =============================================================
def _chip(css, text):
    return f'<span class="chip {css}">{html.escape(text)}</span>'


def member_chips(row):
    key = row["status_key"]
    chips = []
    if key == "active":
        chips.append(_chip("chip-green", "اشتراک فعال"))
        if row["total"]:
            chips.append(_chip("chip-blue", f'{fa(row["sessions_left"])} از {fa(row["total"])} جلسه'))
    elif key == "expired":
        chips.append(_chip("chip-red", "اشتراک منقضی"))
    else:
        chips.append(_chip("chip-gray", "بدون اشتراک"))
    chips.append(_chip("chip-gray", f'آخرین ورود: {last_visit_text(row["days_absent"])}'))
    if row.get("inactive"):
        chips.append(_chip("chip-amber", f"حداقل {fa(INACTIVE_DAYS)} روز غیرفعال"))
    return chips


def _avatar(name):
    return f'<span class="avatar">{html.escape((str(name or "").strip()[:1]) or "؟")}</span>'


def member_card_html(row):
    name = html.escape(str(row["name"] or "—"))
    meta = " · ".join([
        html.escape(str(row["phone"] or "بدون شماره")),
        f'کد ملی {html.escape(str(row["national_id"] or "—"))}',
        f'کد {fa(row["id"])}',
    ])
    return _html(
        '<div class="mg-card">', _avatar(row["name"]), '<div class="mg-main">',
        f'<div class="mg-name">{name}</div>',
        f'<div class="mg-meta">{meta}</div>',
        f'<div class="mg-chips">{"".join(member_chips(row))}</div>',
        "</div></div>",
    )


def archived_card_html(item):
    name = html.escape(str(item["name"] or "—"))
    meta = " · ".join([
        html.escape(str(item["phone"] or "بدون شماره")),
        f'کد ملی {html.escape(str(item["national_id"] or "—"))}',
        f'کد {fa(item["id"])}',
    ])
    chips = [_chip("chip-gray", f'{fa(item["subscriptions"])} اشتراک'), _chip("chip-gray", f'{fa(item["checkins"])} تردد حفظ‌شده')]
    when = ""
    if item.get("archived_at") is not None:
        when = f'آرشیو شده در {jalali_text(to_tehran(item["archived_at"]).date())}'
    return _html(
        '<div class="mg-card">', _avatar(item["name"]), '<div class="mg-main">',
        f'<div class="mg-name">{name}</div>',
        f'<div class="mg-meta">{meta}</div>',
        f'<div class="mg-meta">{when}</div>' if when else "",
        f'<div class="mg-chips">{"".join(chips)}</div>',
        "</div></div>",
    )


def _err_card(title, text):
    return _html('<div class="err-card"><div class="err-icon">!</div><div>',
                 f'<div class="err-title">{title}</div><div class="err-sub">{text}</div>', "</div></div>")


def _result_card(ok, title, text):
    cls, icon = ("ok", "✓") if ok else ("err", "!")
    sub = f'<div class="{cls}-sub">{html.escape(text)}</div>' if text else ""
    return _html(f'<div class="{cls}-card"><div class="{cls}-icon">{icon}</div><div>',
                 f'<div class="{cls}-title">{html.escape(title)}</div>', sub, "</div></div>")


def dz_card_html(counts, archived_count):
    extra = f" (شامل {fa(archived_count)} عضو آرشیوشده)" if archived_count else ""
    stats = "".join(
        f'<div class="dz-stat"><b>{fa(value)}</b><span>{label}</span></div>'
        for label, value in (("عضو" + extra, counts["members"]), ("اشتراک", counts["subscriptions"]), ("تردد", counts["checkins"]))
    )
    return _html(
        '<div class="dz-card"><div class="dz-head"><div class="err-icon">!</div><div>',
        '<div class="dz-title">پاکسازی کامل اطلاعات باشگاه</div>',
        '<div class="dz-sub">همه اعضا (از جمله آرشیو)، اشتراک‌ها و ترددهای این باشگاه برای همیشه پاک می‌شود و قابل بازگشت نیست. '
        "حساب کاربری شما باقی می‌ماند.</div></div></div>",
        f'<div class="dz-stats">{stats}</div></div>',
    )


# =============================================================
# دکمه‌ها
# =============================================================
def _action_button(label, key, type_="primary", disabled=False):
    """دکمه تمام‌عرض با پشتیبانی از disabled؛ سازگار با نسخه‌های قدیمی و جدید Streamlit"""
    try:
        return st.button(label, key=key, type=type_, width="stretch", disabled=disabled)
    except TypeError:
        return st.button(label, key=key, type=type_, use_container_width=True, disabled=disabled)


# =============================================================
# وضعیت صفحه: کارت نتیجه (با لغو)، عملیات در انتظار تأیید
# =============================================================
def _set_last(ok, title, text="", undo=None):
    """کارت نتیجه (بالای صفحه) + یک toast تا وقتی کاربر پایین لیست است هم نتیجه را ببیند"""
    st.session_state.mg_last = {"ok": ok, "title": title, "text": text, "undo": undo, "at": datetime.now(TEHRAN)}
    st.session_state.mg_toast = (title, "✅" if ok else "⚠️")


def _who(names):
    return f"«{names[0]}»" if len(names) == 1 else f"{fa(len(names))} عضو"


def _ask(club_id, kind, targets, section, extra=None):
    """ثبت یک عملیات در انتظار تأیید (کارت تأیید در همان صفحه زیر همان عضو نمایش داده می‌شود)"""
    ids = [t["id"] for t in targets]
    impact = get_members_impact(ids, club_id) if kind in ("archive", "bulk_archive", "delete") else None
    st.session_state.mg_pending = {
        "kind": kind, "ids": ids, "names": [t["name"] for t in targets], "impact": impact,
        "extra": extra or {}, "section": section, "can_archive": archive_supported(),
    }
    st.rerun()


def _current_pending(section):
    """عملیات در انتظار این بخش؛ اگر مال بخش دیگری باشد کنار گذاشته می‌شود"""
    p = st.session_state.get("mg_pending")
    if p and p.get("section") != section:
        st.session_state.pop("mg_pending", None)
        return None
    return p


def _execute(club_id, p):
    """اجرای عملیات تأییدشده و ساخت کارت نتیجه"""
    kind, ids, names = p["kind"], p["ids"], p["names"]
    who = _who(names)
    st.session_state.pop("mg_pending", None)

    if kind in ("archive", "bulk_archive"):
        res = archive_members(ids, club_id)
        if res["ok"]:
            _set_last(True, f"{who} آرشیو شد",
                      "سابقه (اشتراک‌ها و ترددها) حفظ شده و از بخش «آرشیو» می‌توانید برگردانید.",
                      undo={"type": "restore", "ids": ids})
        else:
            _set_last(False, "آرشیو انجام نشد", res["message"])
    elif kind == "delete":
        res = delete_members_permanently(ids, club_id)
        if res["ok"]:
            _set_last(True, f"{who} برای همیشه حذف شد",
                      f'{fa(res["subscriptions"])} اشتراک و {fa(res["checkins"])} تردد او هم پاک شد.')
        else:
            _set_last(False, "حذف انجام نشد", res["message"])
    elif kind == "cancel_sub":
        res = cancel_subscription(ids[0], club_id)
        if res["ok"]:
            _set_last(True, f"اشتراک {who} ابطال شد",
                      f'{fa(res["burned"])} جلسه باقی‌مانده از بین رفت. تا {fa(UNDO_WINDOW_MINUTES)} دقیقه می‌توانید ابطال را لغو کنید.',
                      undo={"type": "restore_sub", "items": res["cancelled"]})
        else:
            _set_last(False, "ابطال انجام نشد", res["message"])
    st.rerun()


def _undo(club_id, undo):
    if undo["type"] == "restore":
        res = restore_members(undo["ids"], club_id)
        if res["ok"]:
            _set_last(True, "عضو به فهرست‌ها برگشت", "آرشیو لغو شد.")
        else:
            _set_last(False, "بازگردانی انجام نشد", res["message"])
    else:
        res = restore_subscription(undo["items"], club_id)
        if res["ok"]:
            _set_last(True, "ابطال اشتراک لغو شد", f'اشتراک دوباره فعال شد و {fa(res["remaining"])} جلسه برگشت.')
        else:
            _set_last(False, "بازگردانی انجام نشد", res["message"])
    st.rerun()


def _render_last(club_id, now):
    last = st.session_state.get("mg_last")
    if not last:
        return
    st.markdown(_result_card(last["ok"], last["title"], last.get("text", "")), unsafe_allow_html=True)
    undo = last.get("undo")
    if undo and (undo["type"] == "restore" or is_undoable(last["at"], now)):
        label = "بازگردانی عضو" if undo["type"] == "restore" else "لغو ابطال اشتراک"
        if _button(label, key="mg_undo"):
            _undo(club_id, undo)


def _render_pending(club_id, p):
    view = pending_view(p)
    title, text = html.escape(view["title"]), html.escape(view["text"])
    st.markdown(_err_card(title, text) if view["tone"] == "err" else _warn_card(title, text), unsafe_allow_html=True)
    c_yes, c_no = st.columns(2)
    with c_yes:
        if _button(view["confirm"], key="mgx_yes" if view["danger"] else "mg_yes", type_="primary"):
            _execute(club_id, p)
    with c_no:
        if _button("انصراف", key="mg_no"):
            st.session_state.pop("mg_pending", None)
            st.rerun()


def _row_box(key):
    """
    قابِ یک عضو: کارت اطلاعات + دکمه‌های همان عضو + کارت تأیید، همه داخل یک کادر.
    اگر نسخه Streamlit پارامتر key را نشناسد، کادر پیش‌فرض (border=True) استفاده می‌شود.
    """
    try:
        return st.container(key=key)
    except TypeError:
        return st.container(border=True)


def _page_limit(section, signature):
    """تعداد کارت‌های قابل‌نمایش؛ با عوض‌شدن جستجو یا فیلتر به حالت اول برمی‌گردد"""
    if st.session_state.get(f"mg_sig_{section}") != signature:
        st.session_state[f"mg_sig_{section}"] = signature
        st.session_state[f"mg_limit_{section}"] = PAGE_SIZE
    return st.session_state.get(f"mg_limit_{section}", PAGE_SIZE)


def _more_button(section, shown, total, limit):
    if total > shown:
        step = min(PAGE_SIZE, total - shown)
        if _button(f"نمایش {fa(step)} مورد بعدی ({fa(total - shown)} مورد باقی‌مانده)", key=f"mg_more_{section}"):
            st.session_state[f"mg_limit_{section}"] = limit + PAGE_SIZE
            st.rerun()


# =============================================================
# بخش ۱: اعضا
# =============================================================
def _render_members(club_id, today, supported):
    members = get_all_members(club_id)
    if not members:
        st.markdown('<div class="ci-empty">هنوز عضو فعالی ثبت نشده است.'
                    + ("<br>اعضای آرشیوشده را در بخش «آرشیو» می‌بینید." if supported else "") + "</div>",
                    unsafe_allow_html=True)
        return

    rows = enrich_rows(
        build_rows(members, logs_from_last(get_last_checkins(club_id)), get_subscription_checkin_counts(club_id), today),
        members, today,
    )
    counts = count_quick(rows)

    quick = st.segmented_control(
        "فیلتر", options=list(QUICK), format_func=lambda k: f"{QUICK[k][0]} ({fa(counts[k])})",
        default="all", key="mg_quick", label_visibility="collapsed",
    ) or "all"
    query = st.text_input(
        "جستجو", placeholder="جستجوی عضو با نام، شماره تماس، کد ملی یا کد عضویت…",
        key="mg_search", label_visibility="collapsed",
    )

    results = apply_filters(rows, quick, query)
    limit = _page_limit("members", (quick, normalize_text(query)))
    visible = results[:limit]
    pending = _current_pending("members")

    # عملیات در انتظارِ عضوی که دیگر در نتایج نیست (جستجو یا فیلتر عوض شده) کنار گذاشته می‌شود
    if pending:
        if pending["kind"] == "bulk_archive":
            stale = quick != "inactive" or sorted(pending["ids"]) != sorted(r["id"] for r in results)
        else:
            stale = pending["ids"][0] not in {r["id"] for r in visible}
        if stale:
            st.session_state.pop("mg_pending", None)
            pending = None

    st.markdown(f'<div class="result-count" style="margin-bottom:12px">{fa(len(results))} عضو نمایش داده می‌شود</div>',
                unsafe_allow_html=True)

    if not results:
        st.info("هیچ عضوی با این مشخصات یافت نشد.")
        return

    if quick == "inactive" and supported:
        st.markdown(_html(
            '<div class="sum-card">',
            f"<b>{fa(len(results))} عضو</b> اشتراک فعال ندارند و حداقل {fa(INACTIVE_DAYS)} روز است تردد نکرده‌اند "
            "(یا هیچ‌وقت نیامده‌اند). می‌توانید همه را یک‌جا آرشیو کنید؛ سابقه‌شان حفظ می‌شود و هر وقت بخواهید برمی‌گردند.",
            "</div>",
        ), unsafe_allow_html=True)
        if _button(f"آرشیو همه نتایج ({fa(len(results))} عضو)", key="mg_bulk"):
            _ask(club_id, "bulk_archive", results, "members")
        if pending and pending["kind"] == "bulk_archive":
            _render_pending(club_id, pending)

    for r in visible:
        with _row_box(f"mgc_{r['id']}"):
            st.markdown(member_card_html(r), unsafe_allow_html=True)
            b_cancel, b_archive, b_delete, _spacer = _columns([1, 1, 1, 1.6])      # ترتیب از راست: ابطال، آرشیو، حذف
            with b_cancel:
                if r["status_key"] == "active" and _button("ابطال اشتراک", key=f"mg_cancel_{r['id']}", type_="secondary"):
                    _ask(club_id, "cancel_sub", [r], "members", {"sessions_left": r["sessions_left"] or 0})
            with b_archive:
                if supported and _button("آرشیو", key=f"mg_arch_{r['id']}", type_="primary"):
                    _ask(club_id, "archive", [r], "members")
            with b_delete:
                if _button("حذف دائمی", key=f"mgd_del_{r['id']}", type_="secondary"):
                    _ask(club_id, "delete", [r], "members")
            if pending and pending["kind"] != "bulk_archive" and pending["ids"] == [r["id"]]:
                _render_pending(club_id, pending)

    _more_button("members", len(visible), len(results), limit)


# =============================================================
# بخش ۲: آرشیو
# =============================================================
def _render_archive(club_id, archived, supported):
    if not supported:
        st.markdown(_warn_card(
            "آرشیو هنوز فعال نشده است",
            "برای فعال‌شدن، فایل migration_archive.sql را یک‌بار در Supabase (بخش SQL Editor) اجرا کنید؛ "
            "بعد از حدود نیم دقیقه این بخش خودکار فعال می‌شود. تا آن موقع فقط «حذف دائمی» در دسترس است.",
        ), unsafe_allow_html=True)
        return
    if not archived:
        st.markdown('<div class="ci-empty">آرشیو خالی است.<br>اعضایی که در بخش «اعضا» آرشیو کنید اینجا می‌آیند '
                    "و هر وقت بخواهید با سابقه کامل برمی‌گردند.</div>", unsafe_allow_html=True)
        return

    query = st.text_input(
        "جستجو در آرشیو", placeholder="جستجو در آرشیو با نام، شماره تماس، کد ملی یا کد عضویت…",
        key="mg_asearch", label_visibility="collapsed",
    )
    results = filter_archived(archived, query)
    limit = _page_limit("archive", normalize_text(query))
    visible = results[:limit]
    pending = _current_pending("archive")
    if pending and pending["ids"][0] not in {i["id"] for i in visible}:
        st.session_state.pop("mg_pending", None)
        pending = None

    st.markdown(f'<div class="result-count" style="margin-bottom:12px">{fa(len(results))} عضو در آرشیو</div>',
                unsafe_allow_html=True)
    if not results:
        st.info("عضوی با این مشخصات در آرشیو پیدا نشد.")
        return

    for item in visible:
        with _row_box(f"mgc_a{item['id']}"):
            st.markdown(archived_card_html(item), unsafe_allow_html=True)
            b_restore, b_delete, _spacer = _columns([1, 1, 2.6])
            with b_restore:
                if _button("بازگردانی", key=f"mg_restore_{item['id']}", type_="primary"):
                    res = restore_members([item["id"]], club_id)
                    if res["ok"]:
                        _set_last(True, f"«{item['name']}» برگشت", "به فهرست اعضا اضافه شد.")
                    else:
                        _set_last(False, "بازگردانی انجام نشد", res["message"])
                    st.rerun()
            with b_delete:
                if _button("حذف دائمی", key=f"mgd_adel_{item['id']}", type_="secondary"):
                    _ask(club_id, "delete", [item], "archive")
            if pending and pending["ids"] == [item["id"]]:
                _render_pending(club_id, pending)

    _more_button("archive", len(visible), len(results), limit)


# =============================================================
# بخش ۳: پاکسازی کامل
# =============================================================
def _backup_tables(club_id, now):
    """
    جدول‌های پشتیبان: اعضا، اشتراک‌ها، ترددها + ai_analytics (تحلیل ریسک ریزش، محاسبه‌شده در همین لحظه).
    اگر جدول ai_analytics در دیتابیس هم ردیفی داشته باشد، جداگانه با نام ai_analytics_table می‌آید.
    """
    tables = export_club_backup(club_id)
    stored = tables.pop("ai_analytics", None)
    try:
        churn = churn_table(predict_churn_risk(club_id), club_id, now)
    except Exception:                                  # تحلیل نباید پشتیبان‌گیری را بشکند
        churn = None
    if churn:
        tables["ai_analytics"] = churn
    if stored and stored[1]:
        tables["ai_analytics_table"] = stored
    return tables


def _get_backup(club_id, counts, today, now):
    """نسخه پشتیبان فقط وقتی دوباره ساخته می‌شود که تعداد داده‌ها عوض شده باشد (تایپ در کادر تأیید پرس‌وجوی تازه نمی‌زند)"""
    signature = tuple(sorted(counts.items()))
    cached = st.session_state.get("mg_backup")
    if not cached or cached["sig"] != signature:
        cached = {"sig": signature, "data": backup_zip(_backup_tables(club_id, now)),
                  "name": f"gym_backup_{today.isoformat()}.zip"}
        st.session_state.mg_backup = cached
    return cached


def _render_cleanup(club_id, archived_count, today, now):
    counts = get_club_counts(club_id)
    st.markdown(dz_card_html(counts, archived_count), unsafe_allow_html=True)

    if counts["members"] + counts["subscriptions"] + counts["checkins"] + counts["analytics"] == 0:
        st.markdown('<div class="ci-empty">اطلاعاتی برای پاک‌کردن وجود ندارد.</div>', unsafe_allow_html=True)
        return

    st.markdown('<div class="as-label">۱. نسخه پشتیبان (پیشنهاد می‌شود)</div>', unsafe_allow_html=True)
    backup = _get_backup(club_id, counts, today, now)
    st.download_button("دانلود نسخه پشتیبان (ZIP)", data=backup["data"], file_name=backup["name"],
                       mime="application/zip", key="mg_download")
    st.caption("شامل CSV اعضا، بسته‌ها، اشتراک‌ها و ترددها، و ai_analytics.csv است. فایل ai_analytics تحلیل ریسک ریزش اعضای "
               "دارای اشتراک فعال (همراه با نوع بسته ۱۲ یا ۲۴ جلسه‌ای) است که همین لحظه از روی سوابق تردد محاسبه می‌شود "
               "(برنامه این امتیازها را در دیتابیس ذخیره نمی‌کند). "
               "رمز عبور در آن نیست. اگر Excel صفر ابتدای شماره‌ها را نشان نداد، فایل سالم است؛ آن را با Data ← From Text/CSV "
               "باز کنید و ستون را Text بگذارید.")

    st.markdown(f'<div class="as-label">۲. برای تأیید، عبارت {RESET_PHRASE} را به انگلیسی بنویسید</div>',
                unsafe_allow_html=True)
    nonce = st.session_state.get("mg_reset_nonce", 0)
    typed = st.text_input("عبارت تأیید", placeholder=RESET_PHRASE, key=f"mg_reset_text_{nonce}",
                          label_visibility="collapsed")
    armed = typed.strip().upper() == RESET_PHRASE

    if _action_button("پاکسازی کامل اطلاعات باشگاه", key="mgx_reset", disabled=not armed):
        if reset_club_data(club_id):
            st.session_state.pop("mg_backup", None)
            st.session_state.pop("mg_pending", None)
            st.session_state.mg_reset_nonce = nonce + 1
            _set_last(True, "اطلاعات باشگاه پاک شد", "همه اعضا (از جمله آرشیو)، اشتراک‌ها و ترددها حذف شدند.")
        else:
            _set_last(False, "پاکسازی انجام نشد", "خطا در ریست دیتابیس؛ چیزی تغییر نکرد. چند لحظه بعد دوباره تلاش کنید.")
        st.rerun()


# =============================================================
# عیب‌یابی سرعت
# =============================================================
def _render_diagnostics():
    with st.expander("بررسی سرعت اتصال به دیتابیس (برای عیب‌یابی)"):
        st.caption("اگر صفحه‌ها کند هستند، این دکمه را بزنید: زمان ساخت اتصال و زمان هر query را اندازه می‌گیرد. "
                   "آدرس و رمز دیتابیس نمایش داده نمی‌شود.")
        if _button("اندازه‌گیری", key="mg_diag", type_="secondary"):
            try:
                st.session_state.mg_diag_result = measure_db_speed()
            except Exception as exc:                       # عیب‌یابی نباید صفحه را بشکند
                st.session_state.mg_diag_result = {"error": f"{type(exc).__name__}"}
        res = st.session_state.get("mg_diag_result")
        if not res:
            return
        if "error" in res:
            st.error(f"اندازه‌گیری انجام نشد ({res['error']}). اتصال به دیتابیس را بررسی کنید.")
            return
        region = f" · منطقه سرور: {res['region']}" if res.get("region") else ""
        st.markdown(_html(
            '<div class="sum-card">',
            f"نوع اتصال: <b>{html.escape(res['mode'])}</b>{html.escape(region)}<br>",
            f"ساخت اتصال تازه: <b>{fa(round(res['new_connection_ms']))} میلی‌ثانیه</b><br>",
            f"هر query روی اتصال آماده: <b>{fa(round(res['roundtrip_ms']))} میلی‌ثانیه</b><br>",
            f"گرفتن اتصال از استخر: <b>{fa(round(res['pool_checkout_ms'], 1))} میلی‌ثانیه</b>",
            "</div>",
        ), unsafe_allow_html=True)
        level, text = speed_verdict(res)
        (st.success if level == "ok" else st.warning)(text)


# =============================================================
# صفحه
# =============================================================
def render_manage(club_id):
    now = datetime.now(TEHRAN)
    today = now.date()
    toast = st.session_state.pop("mg_toast", None)      # toast بعد از rerun نمایش داده می‌شود (مثل پیام خوش‌آمد)
    if toast:
        st.toast(toast[0], icon=toast[1])
    supported = archive_supported()
    archived = get_archived_members(club_id) if supported else []

    st.markdown(
        page_header("مدیریت و حذف", "اعضا را آرشیو یا حذف کنید و اشتراک‌ها را ابطال کنید؛ هر کار قبل از اجرا تأیید می‌گیرد."),
        unsafe_allow_html=True,
    )

    if not supported:
        st.markdown(_warn_card(
            "آرشیو هنوز فعال نشده است",
            "فعلاً فقط «حذف دائمی» در دسترس است. برای فعال‌شدن آرشیو، فایل migration_archive.sql را یک‌بار "
            "در Supabase (بخش SQL Editor) اجرا کنید.",
        ), unsafe_allow_html=True)

    _render_last(club_id, now)

    labels = {
        "members": "اعضا",
        "archive": f"آرشیو ({fa(len(archived))})" if supported else "آرشیو",
        "danger": "پاکسازی کامل",
    }
    section = st.segmented_control(
        "بخش", options=SECTION_KEYS, format_func=lambda k: labels[k],
        default="members", key="mg_section", label_visibility="collapsed",
    ) or "members"

    if section == "members":
        _render_members(club_id, today, supported)
    elif section == "archive":
        _render_archive(club_id, archived, supported)
    else:
        st.session_state.pop("mg_pending", None)
        _render_cleanup(club_id, len(archived), today, now)

    _render_diagnostics()
