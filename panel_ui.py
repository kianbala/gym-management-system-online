"""
رابط کاربری پنل اصلی: سایدبار (ناوبری) و صفحه «داشبورد و اعضا».

منطق صفحه‌های دیگر (ثبت عضو، تردد، بسته، آمار، حذف) در app.py دست‌نخورده می‌ماند.
توابع «خالص» (build_rows / compute_counts / filter_rows / gregorian_to_jalali) بدون Streamlit
قابل تست‌اند.
"""
import html
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db_manager import get_all_members, get_attendance_logs
from ai_analytics import get_subscription_checkin_counts
from ui_styles import PANEL_STYLE

TEHRAN = ZoneInfo("Asia/Tehran")

# آستانه‌های «نیازمند توجه»
ENDING_MAX_SESSIONS = 2   # حداکثر جلسه باقی‌مانده برای «رو به اتمام»
ENDING_MAX_DAYS = 3       # حداکثر روز باقی‌مانده تا انقضا برای «رو به اتمام»
ABSENT_MIN_DAYS = 7       # بیش از این تعداد روز غیبت = «غایب»
ABSENT_WARN_DAYS = 3      # بیش از این تعداد روز غیبت = هشدار زرد در جدول

# کلید داخلی صفحه (همان رشته‌هایی که app.py با آن مسیریابی می‌کند) ← (آیکون، عنوان نمایشی)
MENU = [
    ("داشبورد و اعضا", "📋", "داشبورد و اعضا"),
    ("ثبت عضو جدید", "➕", "ثبت عضو جدید"),
    ("ثبت ورود (تردد)", "✅", "ثبت ورود (تردد)"),
    ("تخصیص بسته", "🎟️", "تخصیص بسته"),
    ("📊 آمار و گزارشات", "📊", "آمار و گزارشات"),
    ("مدیریت و حذف", "🗑️", "مدیریت و حذف"),
]

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_TO_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_FIX_LETTERS = str.maketrans({"ي": "ی", "ك": "ک", "ـ": None})

_JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


# =============================================================
# ابزارهای خالص (بدون Streamlit)
# =============================================================
def fa(value):
    """تبدیل ارقام به فارسی برای نمایش در متن"""
    return str(value).translate(_FA_DIGITS)


def normalize_text(text):
    """یکسان‌سازی ارقام و حروف عربی/فارسی برای جستجو"""
    return str(text or "").translate(_TO_LATIN_DIGITS).translate(_FIX_LETTERS).strip().lower()


def gregorian_to_jalali(gy, gm, gd):
    """تبدیل تاریخ میلادی به شمسی (الگوریتم ۳۳ ساله؛ بدون وابستگی خارجی)"""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy, gy = 979, gy - 1600
    else:
        jy, gy = 0, gy - 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_numeric(d):
    """مثلاً 1405/07/20 (برای جدول)"""
    if not isinstance(d, date):
        return "-"
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    return f"{jy}/{jm:02d}/{jd:02d}"


def jalali_text(d):
    """مثلاً ۲۰ مهر ۱۴۰۵ (برای متن)"""
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    return f"{fa(jd)} {_JALALI_MONTHS[jm - 1]} {fa(jy)}"


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def build_rows(raw_members, attendance_logs, sub_checkins, today):
    """
    تبدیل داده‌های خام دیتابیس به ردیف‌های قابل نمایش.
    نکته: کلیدهای sub_checkins رشته‌اند (خروجی clean_id در ai_analytics)، پس جستجو با str انجام می‌شود.
    """
    last_checkin = {}
    for log in attendance_logs:  # از جدید به قدیم مرتب است؛ اولین مشاهده = آخرین تردد
        mid, ts = log.get("member_id"), log.get("check_in_time")
        if mid is None or not ts or mid in last_checkin:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            last_checkin[mid] = dt.astimezone(TEHRAN).date()
        except (ValueError, TypeError):
            pass

    rows = []
    for m in raw_members:
        sub_id = str(m.get("subscription_id", "-"))
        has_sub = sub_id != "-"
        sessions_left = int(m.get("subscription_days") or 0) if has_sub else None
        end_date = _parse_date(m.get("end_date")) if has_sub else None

        total = None
        if has_sub:
            used = int(sub_checkins.get(sub_id, 0))
            total = sessions_left + used
            total = 24 if total > 12 else 12

        db_status = m.get("status", "EXPIRED")
        if not has_sub:
            status_key = "none"
        elif db_status == "ACTIVE":
            status_key = "active"
        else:
            status_key = "expired"

        days_left = (end_date - today).days if end_date else None
        days_absent = None
        if m.get("id") in last_checkin:
            days_absent = max(0, (today - last_checkin[m["id"]]).days)

        is_active = status_key == "active"
        ending = is_active and (
            (sessions_left is not None and sessions_left <= ENDING_MAX_SESSIONS)
            or (days_left is not None and days_left <= ENDING_MAX_DAYS)
        )
        absent = is_active and days_absent is not None and days_absent > ABSENT_MIN_DAYS

        rows.append({
            "id": m.get("id"),
            "name": m.get("name", ""),
            "national_id": m.get("national_id", ""),
            "phone": m.get("phone", ""),
            "status_key": status_key,
            "ending": ending,
            "absent": absent,
            "sessions_left": sessions_left,
            "total": total,
            "end_date": end_date,
            "days_left": days_left,
            "days_absent": days_absent,
        })
    return rows


# فیلترها: کلید ← (عنوان، شرط)
FILTERS = {
    "all": ("همه", lambda r: True),
    "active": ("فعال", lambda r: r["status_key"] == "active"),
    "ending": ("رو به اتمام", lambda r: r["ending"]),
    "absent": ("غایب", lambda r: r["absent"]),
    "expired": ("منقضی", lambda r: r["status_key"] == "expired"),
    "none": ("فاقد اشتراک", lambda r: r["status_key"] == "none"),
}


def compute_counts(rows):
    return {key: sum(1 for r in rows if pred(r)) for key, (_, pred) in FILTERS.items()}


def filter_rows(rows, flt, query):
    pred = FILTERS.get(flt or "all", FILTERS["all"])[1]
    result = [r for r in rows if pred(r)]
    q = normalize_text(query)
    if q:
        result = [
            r for r in result
            if q in normalize_text(r["name"]) or q in normalize_text(r["national_id"])
            or q in normalize_text(r["phone"]) or q in normalize_text(r["id"])
        ]
    return result


def rows_to_dataframe(rows):
    """
    ردیف‌ها را به جدول نمایشی تبدیل می‌کند.

    نکته مهم (جهت متن): موتور جدول Streamlit جهت هر سلول را از روی «اولین کاراکتر قوی» تعیین می‌کند
    و ایموجی را چپ‌به‌راست حساب می‌کند. اگر ایموجی اول متن باشد، کل سلول چپ‌چین می‌شود.
    پس ایموجی همیشه «آخر» متن می‌آید و متن/تاریخ/اعداد با ارقام فارسی شروع می‌شوند
    (ارقام فارسی راست‌به‌چپ حساب می‌شوند). کدها (کد عضویت، کد ملی، تلفن) لاتین می‌مانند تا کپی راحت باشد.
    """
    def status_text(r):
        if r["status_key"] == "active":
            return "رو به اتمام 🟡" if r["ending"] else "فعال 🟢"
        return "منقضی 🔴" if r["status_key"] == "expired" else "فاقد اشتراک ⚪"

    def absent_text(r):
        d = r["days_absent"]
        if d is None:
            return "بدون تردد"
        mark = " 🔴" if d > ABSENT_MIN_DAYS else (" 🟡" if d > ABSENT_WARN_DAYS else "")
        return f"{fa(d)} روز{mark}"

    return pd.DataFrame([{
        "کد عضویت": r["id"],
        "نام و نام خانوادگی": r["name"],
        "کد ملی": r["national_id"],
        "شماره تماس": r["phone"],
        "وضعیت": status_text(r),
        "جلسات باقی‌مانده": fa(f'{r["sessions_left"]} از {r["total"]}') if r["total"] else "ندارد",
        "تاریخ انقضا": fa(jalali_numeric(r["end_date"])) if r["end_date"] else "ندارد",
        "روزهای غیبت": absent_text(r),
    } for r in rows])


# ترتیب منطقی ستون‌ها از راست به چپ؛ جدول Streamlit چپ‌به‌راست رسم می‌شود پس معکوسش می‌کنیم
_COLUMNS_RTL = [
    "نام و نام خانوادگی", "وضعیت", "جلسات باقی‌مانده", "تاریخ انقضا",
    "روزهای غیبت", "شماره تماس", "کد ملی", "کد عضویت",
]


# =============================================================
# اجزای نمایشی
# =============================================================
def _html(*lines):
    """HTML تک‌خطی (بدون تورفتگی و خط خالی تا مارک‌داون آن را کد تلقی نکند)"""
    return "".join(line.strip() for line in lines)


def page_header(title, subtitle=""):
    sub = f'<div class="page-sub">{subtitle}</div>' if subtitle else ""
    return _html('<div class="page-head">', f'<div class="page-title">{title}</div>', sub, "</div>")


def _kpi(label, value, note, color):
    return _html(
        '<div class="kpi">',
        f'<div class="kpi-label"><span class="kpi-dot" style="background:{color}"></span>{label}</div>',
        f'<div class="kpi-value">{fa(value)}</div>',
        f'<div class="kpi-note">{note}</div>',
        "</div>",
    )


def _kpi_grid(counts, total):
    return _html(
        '<div class="kpi-grid">',
        _kpi("کل اعضا", total, "ثبت‌شده در باشگاه", "#38BDF8"),
        _kpi("اشتراک فعال", counts["active"], f'از {fa(total)} عضو', "#10B981"),
        _kpi("رو به اتمام", counts["ending"], f'{fa(ENDING_MAX_SESSIONS)} جلسه یا {fa(ENDING_MAX_DAYS)} روز مانده', "#F59E0B"),
        _kpi("غایب", counts["absent"], f'بیش از {fa(ABSENT_MIN_DAYS)} روز بدون تردد', "#EF4444"),
        "</div>",
    )


def _stretch_button(label, key, type_="secondary"):
    """دکمه سایدبار تمام‌عرض؛ سازگار با نسخه‌های قدیمی و جدید Streamlit"""
    try:
        return st.sidebar.button(label, key=key, type=type_, width="stretch")
    except TypeError:
        return st.sidebar.button(label, key=key, type=type_, use_container_width=True)


# =============================================================
# سایدبار
# =============================================================
def render_sidebar():
    """نمایش سایدبار و برگرداندن کلید صفحه انتخاب‌شده"""
    club = html.escape(str(st.session_state.club_id))
    user = html.escape(str(st.session_state.username))

    # استایل پنل + کارت باشگاه در یک فراخوانی
    st.sidebar.markdown(PANEL_STYLE + _html(
        '<div class="side-card">',
        '<div class="side-label">باشگاه</div>',
        f'<div class="side-club">{club}</div>',
        f'<div class="side-user">مدیر: {user}</div>',
        "</div>",
    ), unsafe_allow_html=True)

    keys = [k for k, _, _ in MENU]
    if st.session_state.get("nav_choice") not in keys:
        st.session_state.nav_choice = keys[0]

    for i, (key, icon, text) in enumerate(MENU):
        active = st.session_state.nav_choice == key
        if _stretch_button(f"{icon}  {text}", key=f"nav_{i}", type_="primary" if active else "secondary") and not active:
            st.session_state.nav_choice = key
            st.session_state.pop("last_added", None)   # کارت تأیید ثبت عضو فقط تا ترک صفحه می‌ماند
            st.session_state.pop("am_pending", None)
            for _key in ("ci_last", "ci_confirm", "ci_flash", "as_last", "as_member", "as_pkg", "as_flash"):   # وضعیت صفحه‌های ثبت ورود و تخصیص بسته
                st.session_state.pop(_key, None)
            for _key in [k for k in st.session_state.keys() if str(k).startswith("mg_")]:   # وضعیت صفحه مدیریت و حذف
                st.session_state.pop(_key, None)
            st.rerun()

    st.sidebar.divider()
    if _stretch_button("🚪  خروج از حساب", key="logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.club_id = ""
        st.session_state.pop("nav_choice", None)
        st.query_params.clear()
        st.rerun()

    return st.session_state.nav_choice


# =============================================================
# صفحه داشبورد و اعضا
# =============================================================
def render_dashboard(club_id):
    today = datetime.now(TEHRAN).date()
    rows = build_rows(
        get_all_members(club_id),
        get_attendance_logs(club_id),
        get_subscription_checkin_counts(club_id),
        today,
    )

    st.markdown(
        page_header("لیست اعضا و وضعیت اشتراک‌ها", f"امروز {jalali_text(today)} · {fa(len(rows))} عضو"),
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("هنوز عضوی ثبت نشده است. از منوی «ثبت عضو جدید» شروع کنید.")
        return

    counts = compute_counts(rows)
    st.markdown(_kpi_grid(counts, len(rows)), unsafe_allow_html=True)

    selected = st.segmented_control(
        "فیلتر وضعیت",
        options=list(FILTERS),
        format_func=lambda k: f"{FILTERS[k][0]} ({fa(counts[k])})",
        default="all",
        key="dash_filter",
        label_visibility="collapsed",
    )
    query = st.text_input(
        "جستجو",
        placeholder="جستجوی عضو با نام، شماره تماس، کد ملی یا کد عضویت…",
        key="dash_search",
        label_visibility="collapsed",
    )

    shown = filter_rows(rows, selected, query)
    st.markdown(
        _html(f'<div class="result-count">{fa(len(shown))} عضو نمایش داده می‌شود</div>'),
        unsafe_allow_html=True,
    )

    if not shown:
        st.info("هیچ عضوی با این مشخصات یافت نشد.")
        return

    st.dataframe(
        rows_to_dataframe(shown),
        hide_index=True,
        use_container_width=True,
        column_order=list(reversed(_COLUMNS_RTL)),
        column_config={
            "کد عضویت": st.column_config.NumberColumn("کد عضویت", format="%d", width="small"),
            "نام و نام خانوادگی": st.column_config.TextColumn("نام و نام خانوادگی", width="medium"),
            "وضعیت": st.column_config.TextColumn("وضعیت", width="small"),
            "جلسات باقی‌مانده": st.column_config.TextColumn("جلسات باقی‌مانده", width="small"),
            "تاریخ انقضا": st.column_config.TextColumn("تاریخ انقضا", width="small"),
            "روزهای غیبت": st.column_config.TextColumn("روزهای غیبت", width="small"),
        },
    )
