"""
صفحه «ثبت ورود (تردد)».

- تایپ ← کارت نتیجه ← یک‌ضربه «ثبت ورود» (بدون لیست کشویی و بدون انتخاب پیش‌فرض)
- اعضای بدون جلسه هم پیدا می‌شوند (با علت و دکمه «تخصیص بسته»)
- کارت غنی: نوار جلسات، انقضا، آخرین ورود، هشدار تمدید
- هشدار ورود تکراری در همان روز (با تأیید جدا)
- ثبت ورود و کسر جلسه در یک تراکنش (db_manager.check_in_member)
- لغو ورود اشتباه (تا ۱۰ دقیقه) و پنل «ورودهای امروز»
"""
import html
from datetime import datetime, timezone

import streamlit as st

from ai_analytics import get_subscription_checkin_counts
from db_manager import check_in_member, get_all_members, get_last_checkins, get_today_checkins, undo_checkin
from member_ui import _button, _warn_card
from panel_ui import (ABSENT_MIN_DAYS, ENDING_MAX_DAYS, ENDING_MAX_SESSIONS, TEHRAN, _html, build_rows, fa,
                      filter_rows, jalali_text, normalize_text, page_header)

UNDO_WINDOW_MINUTES = 10
MAX_RESULTS = 6
TODAY_LIST_MAX = 8


# =============================================================
# ابزارهای خالص
# =============================================================
def to_tehran(value):
    """datetime یا رشته ISO را به زمان تهران تبدیل می‌کند"""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEHRAN)


def fmt_time(value):
    return fa(to_tehran(value).strftime("%H:%M"))


def is_undoable(value, now=None):
    """آیا هنوز در مهلت لغو (۱۰ دقیقه) هست؟"""
    now = now or datetime.now(TEHRAN)
    age = (now - to_tehran(value)).total_seconds()
    return 0 <= age <= UNDO_WINDOW_MINUTES * 60


def last_visit_text(days_absent):
    if days_absent is None:
        return "بدون سابقه ورود"
    if days_absent == 0:
        return "امروز"
    if days_absent == 1:
        return "دیروز"
    return f"{fa(days_absent)} روز پیش"


def logs_from_last(last_map):
    """آخرین تردد هر عضو را به قالب لاگ‌هایی تبدیل می‌کند که build_rows می‌فهمد (همان منطق داشبورد)"""
    logs = []
    for member_id, value in last_map.items():
        if value is None:
            continue
        logs.append({"member_id": member_id, "check_in_time": value.isoformat() if hasattr(value, "isoformat") else str(value)})
    return logs


def eligibility(row):
    """(آیا می‌تواند وارد شود؟, علت در صورت نه)"""
    if row["status_key"] == "active" and (row["sessions_left"] or 0) > 0:
        return True, None
    if row["status_key"] == "none":
        return False, "فاقد اشتراک"
    if row["status_key"] == "expired":
        return False, "اشتراک منقضی"
    return False, "جلسات تمام شده"


def search_results(rows, query):
    """نتایج جستجو: تطابق دقیق کد عضویت اول، بعد اعضای مجاز به ورود، بعد بقیه"""
    q = normalize_text(query)
    if not q:
        return []
    matches = filter_rows(rows, "all", query)

    def sort_key(r):
        exact_id = q.isdigit() and str(r["id"]) == q
        return (not exact_id, not eligibility(r)[0], normalize_text(r["name"]))

    return sorted(matches, key=sort_key)


# =============================================================
# HTML
# =============================================================
def _chip(css, text):
    return f'<span class="chip {css}">{text}</span>'


def member_chips(row, entered_at=None):
    eligible, reason = eligibility(row)
    chips = []
    if not eligible:
        css = "chip-gray" if row["status_key"] == "none" else "chip-red"
        return [_chip(css, reason)]
    left = row["sessions_left"]
    if left <= ENDING_MAX_SESSIONS:
        chips.append(_chip("chip-amber", f"{fa(left)} جلسه مانده"))
    days_left = row.get("days_left")
    if days_left is not None and 0 <= days_left <= ENDING_MAX_DAYS:
        chips.append(_chip("chip-amber", "امروز آخرین روز اشتراک است" if days_left == 0 else f"{fa(days_left)} روز تا پایان اشتراک"))
    if row["days_absent"] is not None and row["days_absent"] > ABSENT_MIN_DAYS:
        chips.append(_chip("chip-blue", f"بعد از {fa(row['days_absent'])} روز غیبت برگشته"))
    if entered_at is not None:
        chips.append(_chip("chip-blue", f"امروز ساعت {fmt_time(entered_at)} وارد شده"))
    return chips


def member_card_html(row, entered_at=None):
    eligible, _ = eligibility(row)
    name = html.escape(str(row["name"] or "—"))
    meta = f'{html.escape(str(row["phone"] or ""))} · کد {fa(row["id"])}'
    parts = [f'<div class="ci-card{"" if eligible else " ci-card-off"}">',
             f'<div class="ci-top"><span class="ci-name">{name}</span><span class="ci-meta">{meta}</span></div>']

    if eligible and row["total"]:
        pct = max(0, min(100, round(row["sessions_left"] * 100 / row["total"])))
        low = " ci-bar-low" if row["sessions_left"] <= ENDING_MAX_SESSIONS else ""
        parts.append(
            f'<div class="ci-line"><span>{fa(row["sessions_left"])} از {fa(row["total"])} جلسه</span>'
            f'<div class="ci-bar{low}"><div class="ci-bar-fill" style="width:{pct}%"></div></div></div>'
        )

    info = []
    if row["end_date"] is not None:
        info.append(f'انقضا: {jalali_text(row["end_date"])}')
    info.append(f'آخرین ورود: {last_visit_text(row["days_absent"])}')
    parts.append(f'<div class="ci-line">{" · ".join(info)}</div>')

    chips = member_chips(row, entered_at)
    if chips:
        parts.append(f'<div class="ci-chips">{"".join(chips)}</div>')
    parts.append("</div>")
    return _html(*parts)


def checkin_ok_card(last):
    name = html.escape(last["name"])
    remaining = last["remaining"]
    if remaining == 0:
        note = "جلسات این عضو تمام شد؛ برای ورود بعدی باید بسته جدید تخصیص داده شود."
    elif remaining <= ENDING_MAX_SESSIONS:
        note = f"فقط {fa(remaining)} جلسه مانده است؛ تمدید را پیشنهاد دهید."
    else:
        note = ""
    return _html(
        '<div class="ok-card"><div class="ok-icon">✓</div><div>',
        f'<div class="ok-title">{name} وارد شد</div>',
        f'<div class="ok-sub">{fa(remaining)} جلسه مانده · ساعت {fmt_time(last["time"])}',
        f'<br>{note}' if note else "",
        "</div></div></div>",
    )


def today_panel_html(today_list, names):
    unique = len({c["member_id"] for c in today_list})
    head = _html(
        '<div class="today"><div class="today-head"><span class="today-title">ورودهای امروز</span>',
        f'<span class="today-count">{fa(len(today_list))} ورود · {fa(unique)} نفر</span></div>',
    )
    if not today_list:
        return head + '<div class="today-empty">هنوز ورودی ثبت نشده است.</div></div>'
    items = []
    for c in today_list[:TODAY_LIST_MAX]:
        name = html.escape(str(names.get(c["member_id"], "عضو حذف‌شده")))
        items.append(f'<div class="today-item"><span class="today-time">{fmt_time(c["checkin_time"])}</span>'
                     f'<span class="today-name">{name}</span></div>')
    return head + "".join(items) + "</div>"


# =============================================================
# اجرای عملیات
# =============================================================
def _columns(spec):
    try:
        return st.columns(spec, vertical_alignment="center")
    except TypeError:
        return st.columns(spec)


def _do_checkin(club_id, row):
    result = check_in_member(row["id"], club_id)
    if not result["ok"]:
        st.error(result["message"])
        return
    st.session_state.ci_last = {
        "member_id": row["id"], "name": row["name"], "remaining": result["remaining"],
        "checkin_id": result["checkin_id"], "time": result["checkin_time"],
    }
    st.session_state.ci_nonce = st.session_state.get("ci_nonce", 0) + 1     # کادر جستجو برای نفر بعد خالی می‌شود
    st.session_state.pop("ci_confirm", None)
    st.rerun()


def _do_undo(club_id, checkin_id, name):
    result = undo_checkin(checkin_id, club_id, UNDO_WINDOW_MINUTES)
    last = st.session_state.get("ci_last")
    if last and last.get("checkin_id") == checkin_id:
        st.session_state.pop("ci_last", None)
    if result["ok"]:
        st.session_state.ci_flash = ("ok", f"ورود «{name}» لغو شد و یک جلسه برگشت.")
    else:
        st.session_state.ci_flash = ("err", result["message"])
    st.rerun()


def _go_assign(row):
    st.session_state.assign_prefill = row["national_id"]
    st.session_state.nav_choice = "تخصیص بسته"
    for key in ("ci_last", "ci_confirm"):
        st.session_state.pop(key, None)
    st.rerun()


# =============================================================
# صفحه
# =============================================================
def render_checkin(club_id):
    now = datetime.now(TEHRAN)
    today = now.date()

    members = get_all_members(club_id)
    last_map = get_last_checkins(club_id)
    today_list = get_today_checkins(club_id)
    rows = build_rows(members, logs_from_last(last_map), get_subscription_checkin_counts(club_id), today)
    by_id = {r["id"]: r for r in rows}
    names = {r["id"]: r["name"] for r in rows}

    entered_today = {}                       # آخرین ورود امروز هر عضو (لیست از جدید به قدیم است)
    for c in today_list:
        entered_today.setdefault(c["member_id"], c["checkin_time"])

    st.markdown(
        page_header("ثبت ورود ورزشکار", f"امروز {jalali_text(today)} · {fa(len(today_list))} ورود ثبت شده"),
        unsafe_allow_html=True,
    )

    flash = st.session_state.pop("ci_flash", None)
    if flash:
        (st.success if flash[0] == "ok" else st.error)(flash[1])

    col_main, col_side = st.columns([3, 2], gap="large")

    # ---------------- ستون اصلی ----------------
    with col_main:
        last = st.session_state.get("ci_last")
        if last:
            st.markdown(checkin_ok_card(last), unsafe_allow_html=True)
            if is_undoable(last["time"], now):
                if _button("لغو این ورود", key="ci_undo_last"):
                    _do_undo(club_id, last["checkin_id"], last["name"])

        confirm_id = st.session_state.get("ci_confirm")
        if confirm_id is not None:
            target = by_id.get(confirm_id)
            if target is None or not eligibility(target)[0]:
                st.session_state.pop("ci_confirm", None)
            else:
                at = entered_today.get(confirm_id)
                st.markdown(
                    _warn_card("ورود تکراری در یک روز",
                               f"«{html.escape(target['name'])}» امروز ساعت {fmt_time(at) if at else '—'} قبلاً وارد شده است. "
                               "اگر اشتباه نبوده، دوباره ثبت کنید."),
                    unsafe_allow_html=True,
                )
                c_yes, c_no = st.columns(2)
                with c_yes:
                    if _button("بله، دوباره ثبت شود", key="ci_confirm_yes", type_="primary"):
                        _do_checkin(club_id, target)
                with c_no:
                    if _button("انصراف", key="ci_confirm_no"):
                        st.session_state.pop("ci_confirm", None)
                        st.rerun()

        prefill = st.session_state.pop("ci_prefill", None)       # از صفحه تخصیص بسته: جستجو با کد ملی پر می‌شود
        if prefill:
            st.session_state[f"ci_search_{st.session_state.get('ci_nonce', 0)}"] = prefill

        query = st.text_input(
            "جستجوی ورزشکار",
            placeholder="نام، شماره تماس، کد ملی یا کد عضویت را بنویسید…",
            key=f"ci_search_{st.session_state.get('ci_nonce', 0)}",
            label_visibility="collapsed",
        )

        results = search_results(rows, query)
        if not normalize_text(query):
            st.markdown(
                '<div class="ci-empty">برای ثبت ورود، چند حرف از نام یا چند رقم از شماره تماس، کد ملی یا کد عضویت را بنویسید.'
                "<br>نتیجه به‌صورت کارت نمایش داده می‌شود و با یک کلیک ورود ثبت می‌شود.</div>",
                unsafe_allow_html=True,
            )
        elif not results:
            st.info("عضوی با این مشخصات پیدا نشد.")
            if _button("ثبت عضو جدید", key="ci_go_add"):
                st.session_state.nav_choice = "ثبت عضو جدید"
                st.rerun()
        else:
            shown = results[:MAX_RESULTS]
            for r in shown:
                eligible, _ = eligibility(r)
                entered = entered_today.get(r["id"])
                c_info, c_act = _columns([4, 1.4])
                with c_info:
                    st.markdown(member_card_html(r, entered), unsafe_allow_html=True)
                with c_act:
                    if eligible and entered is None:
                        if _button("ثبت ورود", key=f"ci_in_{r['id']}", type_="primary"):
                            _do_checkin(club_id, r)
                    elif eligible:
                        if _button("ثبت ورود دوباره", key=f"ci_again_{r['id']}"):
                            st.session_state.ci_confirm = r["id"]
                            st.rerun()
                    else:
                        if _button("تخصیص بسته", key=f"ci_assign_{r['id']}"):
                            _go_assign(r)
            if len(results) > MAX_RESULTS:
                st.caption(f"{fa(len(results) - MAX_RESULTS)} نتیجه دیگر هم هست؛ برای دقیق‌تر شدن، جستجو را کامل‌تر بنویسید.")

    # ---------------- ستون کناری: ورودهای امروز ----------------
    with col_side:
        st.markdown(today_panel_html(today_list, names), unsafe_allow_html=True)
        undoable = [c for c in today_list[:3] if is_undoable(c["checkin_time"], now)]
        if undoable:
            st.caption(f"لغو ورود اشتباه (تا {fa(UNDO_WINDOW_MINUTES)} دقیقه)")
            for c in undoable:
                name = names.get(c["member_id"], "عضو حذف‌شده")
                c_txt, c_btn = _columns([3, 1])
                with c_txt:
                    st.markdown(f'<div class="today-undo">{fmt_time(c["checkin_time"])} · {html.escape(str(name))}</div>',
                                unsafe_allow_html=True)
                with c_btn:
                    if _button("لغو", key=f"ci_undo_{c['checkin_id']}"):
                        _do_undo(club_id, c["checkin_id"], name)
