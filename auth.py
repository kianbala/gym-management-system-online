import streamlit as st
from db_manager import supabase

# حداقل طول رمز عبور هنگام ثبت‌نام
MIN_PASSWORD_LEN = 6

# یکسان‌سازی حروف عربی/فارسی (ي→ی ، ك→ک ، حذف کشیده)
_PERSIAN_FIX = str.maketrans({"ي": "ی", "ك": "ک", "ـ": None})


def normalize_club_name(name):
    """نرمال‌سازی نام باشگاه: حذف فاصله‌های اضافه و یکسان‌سازی حروف فارسی/عربی"""
    return " ".join((name or "").translate(_PERSIAN_FIX).split())


def authenticate_user(username, password, *args, **kwargs):
    """احراز هویت کاربر و بازگرداندن وضعیت لاگین و شناسه اختصاصی باشگاه"""
    try:
        res = supabase.table("users").select("*").eq("username", username.strip()).eq("password", password.strip()).execute()
        if res.data and len(res.data) > 0:
            user = res.data[0]
            club_id = user.get("club_id", username)
            return True, club_id
        return False, ""
    except Exception as e:
        st.error(f"خطا در احراز هویت: {e}")
        return False, ""


def club_exists(club_id):
    """بررسی اینکه باشگاهی با این شناسه قبلاً ثبت شده است یا نه (در صورت خطا، استثنا پرتاب می‌شود)"""
    res = supabase.table("users").select("id").eq("club_id", club_id).limit(1).execute()
    return bool(res.data)


def register_club(username, password, club_name=None, role="admin"):
    """
    ثبت‌نام مدیر و باشگاه جدید (بدون وابستگی به UI).
    خروجی: (موفق؟, پیام برای کاربر, شناسه باشگاه)
    """
    username = (username or "").strip()
    password = (password or "").strip()
    club_id = normalize_club_name(club_name) or username

    if supabase is None:
        return False, "اتصال به پایگاه داده برقرار نیست. چند لحظه بعد دوباره تلاش کنید.", ""

    try:
        # جلوگیری از ادغام داده‌های دو باشگاه با نام یکسان
        if club_exists(club_id):
            return False, "باشگاهی با این نام قبلاً ثبت شده است. نام دیگری انتخاب کنید یا اگر مدیر آن هستید وارد شوید.", ""

        res = supabase.table("users").insert({
            "username": username,
            "password": password,
            "role": role,
            "club_id": club_id,
        }).execute()

        if res.data:
            return True, "حساب باشگاه ساخته شد.", club_id
        return False, "ساخت حساب انجام نشد. دوباره تلاش کنید.", ""

    except Exception as e:
        err = str(e).lower()
        if "duplicate key" in err or "unique constraint" in err or "23505" in err:
            return False, "این نام کاربری قبلاً ثبت شده است. نام کاربری دیگری انتخاب کنید.", ""
        print(f"Error in register_club: {e}")
        return False, "خطای غیرمنتظره در ساخت حساب. چند لحظه بعد دوباره تلاش کنید.", ""


def add_user(username, password, club_name=None, role="admin", *args, **kwargs):
    """سازگار با نسخه قبلی: ثبت‌نام مدیر جدید و نمایش خطا در UI"""
    ok, msg, _ = register_club(username, password, club_name, role)
    if not ok:
        st.error(msg)
    return ok
