"""صفحه ورود و ثبت‌نام باشگاه (رابط کاربری)"""
import streamlit as st

from auth import (
    authenticate_user,
    register_club,
    normalize_club_name,
    MIN_PASSWORD_LEN,
)
from ui_styles import AUTH_STYLE, AUTH_HERO_HTML, AUTH_POINTS_HTML

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _start_session(username, club_id, welcome):
    """ثبت وضعیت ورود در session و رفتن به پنل اصلی"""
    st.session_state.logged_in = True
    st.session_state.username = username
    st.session_state.club_id = club_id
    st.session_state.welcome_toast = welcome

    # TODO(امنیت): این دو پارامتر بدون بررسی رمز پذیرفته می‌شوند؛ در مرحله بعد با توکن امضاشده جایگزین شود.
    st.query_params["session_club"] = club_id
    st.query_params["session_user"] = username
    st.rerun()


def _validate_registration(username, club_name, password, confirm):
    """اعتبارسنجی فرم ثبت‌نام؛ در صورت مشکل، پیام خطا برمی‌گرداند وگرنه None"""
    if not (username and club_name.strip() and password and confirm):
        return "همه فیلدها را پر کنید."
    if len(username) < 3 or " " in username:
        return "نام کاربری باید حداقل ۳ کاراکتر باشد و فاصله نداشته باشد."
    if len(normalize_club_name(club_name)) < 2:
        return "نام باشگاه باید حداقل ۲ کاراکتر باشد."
    if len(password) < MIN_PASSWORD_LEN:
        return f"رمز عبور باید حداقل {str(MIN_PASSWORD_LEN).translate(_FA_DIGITS)} کاراکتر باشد."
    if password != confirm:
        return "رمز عبور و تکرار آن یکسان نیستند."
    return None


def _login_form():
    with st.form("login_form"):
        username = st.text_input("نام کاربری", placeholder="نام کاربری خود را وارد کنید")
        password = st.text_input("رمز عبور", type="password", placeholder="رمز عبور خود را وارد کنید")
        submitted = st.form_submit_button("ورود", type="primary")

        if submitted:
            username, password = username.strip(), password.strip()
            if not username or not password:
                st.warning("نام کاربری و رمز عبور را وارد کنید.")
                return

            with st.spinner("در حال بررسی اطلاعات..."):
                success, club_id = authenticate_user(username, password)

            if success:
                _start_session(username, club_id, f"خوش آمدید {username}")
            else:
                st.error("نام کاربری یا رمز عبور درست نیست. دوباره بررسی کنید.")


def _register_form():
    with st.form("register_form"):
        username = st.text_input("نام کاربری مدیر", placeholder="مثلاً: ali_gym")
        club_name = st.text_input("نام باشگاه", placeholder="مثلاً: باشگاه آرین")
        password = st.text_input(
            "رمز عبور", type="password",
            placeholder=f"حداقل {str(MIN_PASSWORD_LEN).translate(_FA_DIGITS)} کاراکتر",
        )
        confirm = st.text_input("تکرار رمز عبور", type="password", placeholder="رمز عبور را دوباره وارد کنید")
        submitted = st.form_submit_button("ساخت حساب باشگاه", type="primary")

        if submitted:
            username, password, confirm = username.strip(), password.strip(), confirm.strip()

            error = _validate_registration(username, club_name, password, confirm)
            if error:
                st.error(error)
                return

            with st.spinner("در حال ساخت حساب..."):
                ok, msg, club_id = register_club(username, password, club_name=club_name)

            if ok:
                # ورود خودکار بعد از ساخت حساب
                _start_session(username, club_id, f"حساب باشگاه «{club_id}» ساخته شد. خوش آمدید!")
            else:
                st.error(msg)


def render_auth_page():
    """نمایش کامل صفحه ورود / ثبت‌نام"""
    # استایل + هدر در یک فراخوانی تا فاصله اضافه ایجاد نشود
    st.markdown(AUTH_STYLE + AUTH_HERO_HTML, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["ورود", "ثبت‌نام باشگاه جدید"])
    with tab_login:
        _login_form()
    with tab_register:
        _register_form()

    st.markdown(AUTH_POINTS_HTML, unsafe_allow_html=True)
