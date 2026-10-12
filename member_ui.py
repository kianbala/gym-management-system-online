"""
صفحه «ثبت عضو جدید».

- اعتبارسنجی هوشمند (ارقام فارسی/عربی خودکار به لاتین تبدیل می‌شوند؛ خطا کنار هر فیلد)
- هشدار نرم برای رقم کنترلی کد ملی (با تأیید کاربر؛ مانع ثبت نیست)
- پیام تکراری هوشمند (نام عضو موجود را نشان می‌دهد)
- کارت تأیید بعد از ثبت + دکمه «تخصیص بسته به او»
- فهرست «آخرین اعضای ثبت‌شده»

ثبت عضو و تخصیص بسته عمداً دو کار جدا هستند؛ ثبت عضو هیچ اشتراکی نمی‌سازد.
توابع «خالص» (normalize_* / validate_member / find_duplicate) بدون Streamlit قابل تست‌اند.
"""
import html

import streamlit as st

from db_manager import add_member, get_all_members
from panel_ui import _html, _parse_date, fa, jalali_text, page_header

_TO_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_FIX_LETTERS = str.maketrans({"ي": "ی", "ك": "ک", "ـ": None})

RECENT_COUNT = 5


# =============================================================
# ابزارهای خالص
# =============================================================
def normalize_digits(text):
    """ارقام فارسی و عربی را به لاتین تبدیل می‌کند"""
    return str(text or "").translate(_TO_LATIN_DIGITS)


def normalize_name(text):
    """حذف فاصله‌های اضافه و یکسان‌سازی حروف عربی/فارسی"""
    return " ".join(str(text or "").translate(_FIX_LETTERS).split())


def normalize_phone(text):
    """
    شماره تماس را به قالب ۱۱ رقمی 09xxxxxxxxx نزدیک می‌کند.
    خط تیره، فاصله و پیش‌شماره‌های +98 / 0098 / 98 و ۱۰ رقمی بدون صفر هم پذیرفته می‌شوند.
    """
    digits = "".join(ch for ch in normalize_digits(text) if ch.isdigit())
    if digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits


def normalize_national_id(text):
    return "".join(ch for ch in normalize_digits(text) if ch.isdigit())


def valid_national_id_checksum(national_id):
    """بررسی رقم کنترلی کد ملی ایران (رشته باید ۱۰ رقم لاتین باشد)"""
    n = str(national_id)
    if len(n) != 10 or not n.isascii() or not n.isdigit() or len(set(n)) == 1:
        return False
    s = sum(int(d) * (10 - i) for i, d in enumerate(n[:9]))
    r = s % 11
    return int(n[9]) == (r if r < 2 else 11 - r)


def validate_member(first_name, last_name, national_id, phone):
    """
    اعتبارسنجی فرم. خروجی: (مقادیر تمیز، دیکشنری خطاها، هشدار رقم کنترلی؟)
    خطاها کلیدی به نام فیلد دارند: first_name / last_name / national_id / phone
    """
    cleaned = {
        "first_name": normalize_name(first_name),
        "last_name": normalize_name(last_name),
        "national_id": normalize_national_id(national_id),
        "phone": normalize_phone(phone),
    }
    errors = {}
    if not cleaned["first_name"]:
        errors["first_name"] = "نام را وارد کنید."
    if not cleaned["last_name"]:
        errors["last_name"] = "نام خانوادگی را وارد کنید."

    nid = cleaned["national_id"]
    if not nid:
        errors["national_id"] = "کد ملی را وارد کنید."
    elif len(nid) != 10:
        errors["national_id"] = f"کد ملی باید ۱۰ رقم باشد ({fa(len(nid))} رقم وارد شده). صفرهای ابتدای آن را هم بنویسید."

    ph = cleaned["phone"]
    if not ph:
        errors["phone"] = "شماره تماس را وارد کنید."
    elif len(ph) != 11 or not ph.startswith("09"):
        errors["phone"] = "شماره تماس باید ۱۱ رقم باشد و با ۰۹ شروع شود (مثلاً 09123456789)."

    checksum_warning = "national_id" not in errors and not valid_national_id_checksum(nid)
    cleaned["full_name"] = f'{cleaned["first_name"]} {cleaned["last_name"]}'.strip()
    return cleaned, errors, checksum_warning


def find_duplicate(members, national_id, phone):
    """
    اگر کد ملی یا شماره تماس قبلاً ثبت شده باشد، (فیلد، عضو موجود) برمی‌گرداند.
    مقایسه بعد از یکسان‌سازی ارقام انجام می‌شود تا ردیف‌های قدیمیِ با ارقام فارسی هم پیدا شوند.
    """
    for m in members:
        if national_id and normalize_national_id(m.get("national_id")) == national_id:
            return "national_id", m
        if phone and normalize_phone(m.get("phone")) == phone:
            return "phone", m
    return None


def duplicate_message(field, member):
    what = "کد ملی" if field == "national_id" else "شماره تماس"
    name = html.escape(str(member.get("name") or "عضو بدون نام"))
    return f"این {what} قبلاً برای «{name}» (کد عضویت {fa(member.get('id'))}) ثبت شده است."


# =============================================================
# اجزای نمایشی
# =============================================================
def _status_chip(m):
    has_sub = str(m.get("subscription_id", "-")) != "-"
    if not has_sub:
        return "chip-gray", "بدون اشتراک"
    if m.get("status") == "ACTIVE" and int(m.get("subscription_days") or 0) > 0:
        return "chip-green", "فعال"
    return "chip-red", "منقضی"


def recent_members_html(members, highlight_id=None):
    """فهرست آخرین اعضا (get_all_members از جدید به قدیم مرتب است)"""
    if not members:
        return _html('<div class="recent">', '<div class="recent-title">آخرین اعضای ثبت‌شده</div>',
                     '<div class="recent-empty">هنوز عضوی ثبت نشده است.</div>', "</div>")
    items = []
    for m in members[:RECENT_COUNT]:
        name = str(m.get("name") or "—")
        joined = _parse_date(m.get("join_date"))
        sub = f"{jalali_text(joined)} · کد {fa(m.get('id'))}" if joined else f"کد {fa(m.get('id'))}"
        chip_cls, chip_text = _status_chip(m)
        new_cls = " recent-new" if highlight_id is not None and m.get("id") == highlight_id else ""
        items.append(_html(
            f'<div class="recent-item{new_cls}">',
            f'<span class="avatar">{html.escape(name[:1])}</span>',
            f'<div class="r-main"><div class="r-name">{html.escape(name)}</div><div class="r-sub">{sub}</div></div>',
            f'<span class="chip {chip_cls}">{chip_text}</span>',
            "</div>",
        ))
    return _html('<div class="recent">', '<div class="recent-title">آخرین اعضای ثبت‌شده</div>', *items, "</div>")


def _ok_card(last):
    name = html.escape(last["name"])
    return _html(
        '<div class="ok-card"><div class="ok-icon">✓</div><div>',
        f'<div class="ok-title">{name} ثبت شد</div>',
        f'<div class="ok-sub">کد عضویت {fa(last["id"])} · {last["phone"]}<br>'
        'هنوز اشتراکی ندارد. برای شروع تمرین، یک بسته به او تخصیص دهید.</div>',
        "</div></div>",
    )


def _warn_card(title, text):
    return _html('<div class="warn-card"><div class="warn-icon">!</div><div>',
                 f'<div class="warn-title">{title}</div><div class="warn-sub">{text}</div>', "</div></div>")


def _button(label, key, type_="secondary"):
    """دکمه تمام‌عرض؛ سازگار با نسخه‌های قدیمی و جدید Streamlit"""
    try:
        return st.button(label, key=key, type=type_, width="stretch")
    except TypeError:
        return st.button(label, key=key, type=type_, use_container_width=True)


def _submit_button(label):
    try:
        return st.form_submit_button(label, type="primary", width="stretch")
    except TypeError:
        return st.form_submit_button(label, type="primary", use_container_width=True)


# =============================================================
# منطق ثبت
# =============================================================
def _try_add(club_id, cleaned):
    """چک تکراری + ثبت. در موفقیت st.rerun() صدا زده می‌شود؛ در خطا False برمی‌گرداند."""
    members = get_all_members(club_id)
    dup = find_duplicate(members, cleaned["national_id"], cleaned["phone"])
    if dup:
        st.error(duplicate_message(*dup))
        return False

    ok, msg = add_member(cleaned["full_name"], cleaned["phone"], cleaned["national_id"], club_id, subscription_days=0)
    if not ok:
        st.error(msg)
        return False

    # شناسه عضو جدید را از فهرست تازه پیدا می‌کنیم (add_member شناسه برنمی‌گرداند)
    new_id = None
    for m in get_all_members(club_id):
        if normalize_national_id(m.get("national_id")) == cleaned["national_id"]:
            new_id = m.get("id")
            break

    st.session_state.last_added = {
        "id": new_id, "name": cleaned["full_name"], "phone": cleaned["phone"],
        "national_id": cleaned["national_id"],
    }
    st.session_state.am_nonce = st.session_state.get("am_nonce", 0) + 1   # فیلدهای فرم خالی می‌شوند
    st.session_state.pop("am_pending", None)
    st.rerun()
    return True


# =============================================================
# صفحه
# =============================================================
def render_add_member(club_id):
    st.markdown(
        page_header("ثبت عضو جدید", "اطلاعات اولیه عضو را وارد کنید. اشتراک را بعد از ثبت، جداگانه تخصیص می‌دهید."),
        unsafe_allow_html=True,
    )

    col_form, col_side = st.columns([3, 2], gap="large")
    last = st.session_state.get("last_added")
    members = get_all_members(club_id)

    # ---------------- ستون اصلی: فرم ----------------
    with col_form:
        if last:
            st.markdown(_ok_card(last), unsafe_allow_html=True)
            c_assign, c_more = st.columns(2)
            with c_assign:
                if _button("تخصیص بسته به او", key="am_assign", type_="primary"):
                    st.session_state.assign_prefill = last["national_id"]
                    st.session_state.nav_choice = "تخصیص بسته"
                    st.session_state.pop("last_added", None)
                    st.rerun()
            with c_more:
                if _button("ثبت عضو دیگر", key="am_another"):
                    st.session_state.pop("last_added", None)
                    st.rerun()

        # هشدار رقم کنترلی کد ملی: اجازه ثبت با تأیید کاربر
        pending = st.session_state.get("am_pending")
        if pending:
            st.markdown(
                _warn_card("کد ملی معتبر به نظر نمی‌رسد",
                           f'رقم کنترلی کد ملی {pending["national_id"]} درست نیست. '
                           "اگر اشتباه تایپ شده، آن را اصلاح کنید؛ اگر مطمئن هستید، با همین کد ثبت کنید."),
                unsafe_allow_html=True,
            )
            c_yes, c_no = st.columns(2)
            with c_yes:
                if _button("ثبت با همین کد ملی", key="am_confirm", type_="primary"):
                    _try_add(club_id, pending)
            with c_no:
                if _button("اصلاح کد ملی", key="am_cancel"):
                    st.session_state.pop("am_pending", None)
                    st.rerun()

        nonce = st.session_state.get("am_nonce", 0)
        with st.form("add_member_form", clear_on_submit=False):
            r1a, r1b = st.columns(2)
            with r1a:
                first_name = st.text_input("نام", placeholder="مثلاً: علی", key=f"am_first_{nonce}")
                slot_first = st.empty()
            with r1b:
                last_name = st.text_input("نام خانوادگی", placeholder="مثلاً: رضایی", key=f"am_last_{nonce}")
                slot_last = st.empty()
            r2a, r2b = st.columns(2)
            with r2a:
                national_id = st.text_input("کد ملی", placeholder="۱۰ رقم، مثلاً 0012345678", key=f"am_nid_{nonce}")
                slot_nid = st.empty()
            with r2b:
                phone = st.text_input("شماره تماس", placeholder="مثلاً 09123456789", key=f"am_phone_{nonce}")
                slot_phone = st.empty()
            submitted = _submit_button("ثبت عضو")

            if submitted:
                st.session_state.pop("am_pending", None)
                cleaned, errors, checksum_warning = validate_member(first_name, last_name, national_id, phone)
                slots = {"first_name": slot_first, "last_name": slot_last, "national_id": slot_nid, "phone": slot_phone}
                for field, message in errors.items():
                    slots[field].markdown(f'<div class="field-error">{message}</div>', unsafe_allow_html=True)

                if not errors:
                    if checksum_warning:
                        st.session_state.am_pending = cleaned
                        st.rerun()
                    else:
                        _try_add(club_id, cleaned)

    # ---------------- ستون کناری: آخرین اعضا ----------------
    with col_side:
        highlight = last["id"] if last else None
        st.markdown(recent_members_html(members, highlight), unsafe_allow_html=True)
