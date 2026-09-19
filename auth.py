import streamlit as st
from db_manager import supabase

def authenticate_user(username, password, *args, **kwargs):
    """احراز هویت کاربر و بازگرداندن وضعیت لاگین و شناسه اختصاصی باشگاه"""
    try:
        res = supabase.table("users").select("*").eq("username", username.strip()).eq("password", password.strip()).execute()
        if res.data and len(res.data) > 0:
            user = res.data[0]
            # دریافت نام باشگاه (در صورت عدم وجود، همان username بازگردانده می‌شود)
            club_id = user.get("club_id", username)
            return True, club_id
        return False, ""
    except Exception as e:
        st.error(f"خطا در احراز هویت: {e}")
        return False, ""

def add_user(username, password, club_name=None, role="admin", *args, **kwargs):
    """ثبت نام مدیر جدید با نام کاربری یکتا و UUID خودکار"""
    try:
        # اگر نام باشگاه وارد نشده باشد، از همان نام کاربری استفاده می‌شود
        club_id = club_name.strip() if club_name and club_name.strip() else username.strip()

        data = {
            "username": username.strip(),
            "password": password.strip(),
            "role": role,
            "club_id": club_id
            # شناسه id به صورت خودکار توسط UUID در Supabase تولید می‌شود
        }
        res = supabase.table("users").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        err_msg = str(e)
        if "duplicate key value" in err_msg or "unique constraint" in err_msg:
            st.error("⚠️ این نام کاربری قبلاً ثبت شده است. لطفاً نام کاربری دیگری انتخاب کنید.")
        else:
            st.error(f"خطا در ساخت حساب: {e}")
        return False