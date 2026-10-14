"""
صفحه «تخصیص بسته».

- جستجو ← کارت عضو ← انتخاب بسته (۱۲ یا ۲۴ جلسه) ← خلاصه ← فعال‌سازی (بدون انتخاب پیش‌فرض)
- بدون قیمت؛ بسته‌ها ثابت و ۳۰ روزه‌اند (بخش آمار روی همین دو نوع بسته حساب می‌شود)
- قانون: فقط وقتی جلسات تمام شده یا اشتراک منقضی شده بسته جدید ثبت می‌شود (تمدید زودهنگام وجود ندارد)
- کارت تأیید + میان‌بر «ثبت ورود برای او»، تاریخچه ۳ اشتراک آخر، لغو تخصیص اشتباه (تا ۱۰ دقیقه)
"""
import html
from datetime import datetime, timedelta

import streamlit as st

from ai_analytics import get_subscription_checkin_counts
from checkin_ui import _columns, fmt_time, last_visit_text, logs_from_last, to_tehran
from db_manager import (assign_package, get_all_members, get_last_checkins, get_member_subscriptions,
                        undo_assignment)
from member_ui import _button, _warn_card
from panel_ui import TEHRAN, _html, _parse_date, build_rows, fa, filter_rows, jalali_text, normalize_text, page_header

PACKAGES = {12: "بسته ۱", 24: "بسته ۲"}      # تعداد جلسه ← نام بسته
VALIDITY_DAYS = 30
UNDO_WINDOW_MINUTES = 10
MAX_RESULTS = 6


# =============================================================
# ابزارهای خالص
# =============================================================
def can_assign(row):
    """بسته جدید فقط وقتی مجاز است که عضو اشتراکِ فعالِ دارای جلسه نداشته باشد"""
    return not (row["status_key"] == "active" and (row["sessions_left"] or 0) > 0)


def package_label(sessions):
    return f"{PACKAGES[sessions]} · {fa(sessions)} جلسه"


def search_results(rows, query):
    """نتایج جستجو: تطابق دقیق کد عضویت اول، بعد اعضای مجاز به دریافت بسته، بعد بقیه"""
    q = normalize_text(query)
    if not q:
        return []

    def sort_key(r):
        return (not (q.isdigit() and str(r["id"]) == q), not can_assign(r), normalize_text(r["name"]))

    return sorted(filter_rows(rows, "all", query), key=sort_key)


def within_undo_window(value, now=None):
    now = now or datetime.now(TEHRAN)
    return 0 <= (now - to_tehran(value)).total_seconds() <= UNDO_WINDOW_MINUTES * 60


def history_status(sub, today):
    """وضعیت یک اشتراک در تاریخچه: (کلاس چیپ، متن)"""
    end = _parse_date(sub.get("end_date"))
    remaining = sub.get("remaining") or 0
    if sub.get("status") == "ACTIVE" and remaining > 0 and (end is None or end >= today):
        return "chip-green", "فعال"
    if remaining <= 0:
        return "chip-gray", "جلسات تمام شد"
    return "chip-red", "منقضی"


# =============================================================
# HTML
# =============================================================
def _chip(css, text):
    return f'<span class="chip {css}">{text}</span>'


def assign_card_html(row):
    name = html.escape(str(row["name"] or "—"))
    meta = f'{html.escape(str(row["phone"] or ""))} · کد {fa(row["id"])}'
    if row["status_key"] == "active" and (row["sessions_left"] or 0) > 0:
        chip = _chip("chip-green", f'اشتراک فعال · {fa(row["sessions_left"])} جلسه مانده')
    elif row["status_key"] == "active":
        chip = _chip("chip-red", "جلسات تمام شده")
    elif row["status_key"] == "expired":
        chip = _chip("chip-red", "اشتراک منقضی")
    else:
        chip = _chip("chip-gray", "بدون اشتراک")

    info = []
    if row["end_date"] is not None:
        info.append(f'انقضا: {jalali_text(row["end_date"])}')
    info.append(f'آخرین ورود: {last_visit_text(row["days_absent"])}')
    return _html(
        '<div class="ci-card">',
        f'<div class="ci-top"><span class="ci-name">{name}</span><span class="ci-meta">{meta}</span></div>',
        f'<div class="ci-line">{" · ".join(info)}</div>',
        f'<div class="ci-chips">{chip}</div>',
        "</div>",
    )


def package_summary_html(name, sessions, today):
    end = today + timedelta(days=VALIDITY_DAYS)
    return _html(
        '<div class="sum-card">',
        f'برای «{html.escape(str(name))}» <b>{PACKAGES[sessions]} ({fa(sessions)} جلسه)</b> ',
        f'از امروز {jalali_text(today)} تا {jalali_text(end)} فعال می‌شود ({fa(VALIDITY_DAYS)} روز اعتبار).',
        "</div>",
    )


def assign_ok_card(last):
    name = html.escape(str(last["name"]))
    return _html(
        '<div class="ok-card"><div class="ok-icon">✓</div><div>',
        f'<div class="ok-title">{PACKAGES[last["sessions"]]} ({fa(last["sessions"])} جلسه) برای {name} فعال شد</div>',
        f'<div class="ok-sub">از {jalali_text(last["start_date"])} تا {jalali_text(last["end_date"])} · ساعت {fmt_time(last["time"])}</div>',
        "</div></div>",
    )


def history_html(subs, today):
    if not subs:
        return _html('<div class="recent"><div class="recent-title">تاریخچه اشتراک‌ها</div>',
                     '<div class="recent-empty">این عضو هنوز اشتراکی نداشته است.</div></div>')
    items = []
    for s in subs:
        sessions = 24 if (s.get("remaining") or 0) + (s.get("used") or 0) > 12 else 12
        css, text = history_status(s, today)
        start, end = _parse_date(s.get("start_date")), _parse_date(s.get("end_date"))
        period = f'{jalali_text(start)} تا {jalali_text(end)}' if start and end else "—"
        items.append(_html(
            '<div class="hist-item"><div class="hist-main">',
            f'<div class="hist-title">{package_label(sessions)}</div>',
            f'<div class="hist-sub">{period} · {fa(s.get("used") or 0)} از {fa(sessions)} جلسه مصرف شد</div>',
            f'</div>{_chip(css, text)}</div>',
        ))
    return _html('<div class="recent"><div class="recent-title">تاریخچه اشتراک‌ها</div>', *items, "</div>")


GUIDE_HTML = _html(
    '<div class="recent"><div class="recent-title">مراحل تخصیص بسته</div>',
    '<div class="guide-step"><span class="guide-num">۱</span><span>عضو را با نام، شماره تماس، کد ملی یا کد عضویت جستجو و انتخاب کنید.</span></div>',
    '<div class="guide-step"><span class="guide-num">۲</span><span>یکی از دو بسته (۱۲ یا ۲۴ جلسه‌ای) را انتخاب کنید و خلاصه را بخوانید.</span></div>',
    '<div class="guide-step"><span class="guide-num">۳</span><span>«فعال‌سازی بسته» را بزنید. اگر اشتباه شد، تا ۱۰ دقیقه می‌توانید لغوش کنید.</span></div>',
    '<div class="guide-note">بسته جدید فقط وقتی ثبت می‌شود که جلسات عضو تمام شده یا اشتراکش منقضی شده باشد.</div>',
    "</div>",
)


# =============================================================
# اجرای عملیات
# =============================================================
def _go_checkin(national_id):
    st.session_state.ci_prefill = national_id
    st.session_state.nav_choice = "ثبت ورود (تردد)"
    for key in ("as_last", "as_member", "as_pkg"):
        st.session_state.pop(key, None)
    st.rerun()


def _activate(club_id, row, sessions):
    result = assign_package(row["id"], club_id, sessions, VALIDITY_DAYS)
    if not result["ok"]:
        st.session_state.as_flash = ("err", result["message"])
        st.rerun()
        return
    st.session_state.as_last = {
        "subscription_id": result["subscription_id"], "name": row["name"], "national_id": row["national_id"],
        "sessions": sessions, "start_date": result["start_date"], "end_date": result["end_date"],
        "time": datetime.now(TEHRAN),
    }
    st.session_state.pop("as_member", None)
    st.session_state.pop("as_pkg", None)
    st.session_state.as_nonce = st.session_state.get("as_nonce", 0) + 1
    st.rerun()


def _undo(club_id, last):
    result = undo_assignment(last["subscription_id"], club_id, UNDO_WINDOW_MINUTES)
    st.session_state.pop("as_last", None)
    if result["ok"]:
        st.session_state.as_flash = ("ok", f"تخصیص بسته «{last['name']}» لغو شد.")
    else:
        st.session_state.as_flash = ("err", result["message"])
    st.rerun()


def _select_member(row):
    st.session_state.as_member = row["id"]
    st.session_state.pop("as_pkg", None)
    st.session_state.as_nonce = st.session_state.get("as_nonce", 0) + 1     # کادر جستجو خالی می‌شود
    st.rerun()


# =============================================================
# صفحه
# =============================================================
def _render_selected(club_id, row, today):
    c_label, c_change = _columns([3, 1])
    with c_label:
        st.markdown('<div class="as-label">عضو انتخاب‌شده</div>', unsafe_allow_html=True)
    with c_change:
        if _button("تغییر عضو", key="as_change"):
            st.session_state.pop("as_member", None)
            st.session_state.pop("as_pkg", None)
            st.rerun()

    st.markdown(assign_card_html(row), unsafe_allow_html=True)

    if not can_assign(row):
        end = jalali_text(row["end_date"]) if row["end_date"] is not None else "—"
        st.markdown(
            _warn_card("این عضو هنوز جلسه دارد",
                       f'{fa(row["sessions_left"])} جلسه تا {end} باقی مانده است. بعد از تمام شدن جلسات یا انقضای '
                       "اشتراک می‌توانید بسته جدید ثبت کنید."),
            unsafe_allow_html=True,
        )
        if _button("ثبت ورود برای او", key="as_go_ci_sel", type_="primary"):
            _go_checkin(row["national_id"])
        return

    st.markdown('<div class="as-label">انتخاب بسته</div>', unsafe_allow_html=True)
    chosen = st.session_state.get("as_pkg")
    c_a, c_b = st.columns(2)
    for col, sessions in ((c_a, 12), (c_b, 24)):
        with col:
            if _button(package_label(sessions), key=f"as_choose_{sessions}", type_="primary" if chosen == sessions else "secondary"):
                st.session_state.as_pkg = sessions
                st.rerun()

    if chosen in PACKAGES:
        st.markdown(package_summary_html(row["name"], chosen, today), unsafe_allow_html=True)
        if _button("فعال‌سازی بسته", key="as_activate", type_="primary"):
            _activate(club_id, row, chosen)
    else:
        st.caption("یکی از دو بسته را انتخاب کنید.")


def render_assign(club_id):
    now = datetime.now(TEHRAN)
    today = now.date()

    rows = build_rows(
        get_all_members(club_id),
        logs_from_last(get_last_checkins(club_id)),
        get_subscription_checkin_counts(club_id),
        today,
    )
    by_id = {r["id"]: r for r in rows}

    # ورود از صفحه‌های «ثبت عضو» یا «ثبت ورود»: عضو با کد ملی مستقیم انتخاب می‌شود
    prefill = st.session_state.pop("assign_prefill", None)
    if prefill:
        key = normalize_text(prefill)
        match = next((r for r in rows if normalize_text(r["national_id"]) == key), None)
        if match:
            st.session_state.as_member = match["id"]
            st.session_state.pop("as_pkg", None)
            st.session_state.pop("as_last", None)

    selected = by_id.get(st.session_state.get("as_member"))
    if st.session_state.get("as_member") is not None and selected is None:
        st.session_state.pop("as_member", None)             # عضو حذف شده

    st.markdown(
        page_header("تخصیص بسته به عضو", "برای عضوی که جلساتش تمام شده یا اشتراکش منقضی شده، بسته جدید فعال کنید."),
        unsafe_allow_html=True,
    )
    flash = st.session_state.pop("as_flash", None)
    if flash:
        (st.success if flash[0] == "ok" else st.error)(flash[1])

    col_main, col_side = st.columns([3, 2], gap="large")

    with col_main:
        last = st.session_state.get("as_last")
        if last:
            st.markdown(assign_ok_card(last), unsafe_allow_html=True)
            c_ci, c_more = st.columns(2)
            with c_ci:
                if _button("ثبت ورود برای او", key="as_go_ci_last", type_="primary"):
                    _go_checkin(last["national_id"])
            with c_more:
                if _button("تخصیص بسته به عضو دیگر", key="as_more"):
                    st.session_state.pop("as_last", None)
                    st.rerun()
            if within_undo_window(last["time"], now):
                if _button("لغو این تخصیص", key="as_undo_last"):
                    _undo(club_id, last)

        if selected is not None:
            _render_selected(club_id, selected, today)
        else:
            query = st.text_input(
                "جستجوی ورزشکار",
                placeholder="نام، شماره تماس، کد ملی یا کد عضویت را بنویسید…",
                key=f"as_search_{st.session_state.get('as_nonce', 0)}",
                label_visibility="collapsed",
            )
            if not normalize_text(query):
                st.markdown('<div class="ci-empty">برای تخصیص بسته، ابتدا عضو را جستجو کنید.</div>', unsafe_allow_html=True)
            else:
                results = search_results(rows, query)
                if not results:
                    st.info("عضوی با این مشخصات پیدا نشد.")
                    if _button("ثبت عضو جدید", key="as_go_add"):
                        st.session_state.nav_choice = "ثبت عضو جدید"
                        st.rerun()
                for r in results[:MAX_RESULTS]:
                    c_info, c_act = _columns([4, 1.4])
                    with c_info:
                        st.markdown(assign_card_html(r), unsafe_allow_html=True)
                    with c_act:
                        if can_assign(r):
                            if _button("انتخاب", key=f"as_pick_{r['id']}", type_="primary"):
                                _select_member(r)
                        else:
                            if _button("ثبت ورود", key=f"as_ci_{r['id']}"):
                                _go_checkin(r["national_id"])
                if len(results) > MAX_RESULTS:
                    st.caption(f"{fa(len(results) - MAX_RESULTS)} نتیجه دیگر هم هست؛ برای دقیق‌تر شدن، جستجو را کامل‌تر بنویسید.")

    with col_side:
        if selected is not None:
            st.markdown(history_html(get_member_subscriptions(selected["id"], club_id, 3), today), unsafe_allow_html=True)
        else:
            st.markdown(GUIDE_HTML, unsafe_allow_html=True)
