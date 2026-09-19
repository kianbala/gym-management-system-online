import streamlit as st
from db_manager import supabase

def authenticate_user(username, password, *args, **kwargs):
    """احراز هویت کاربر و بازگرداندن وضعیت لاگین و شناسه اختصاصی باشگاه"""
    try:
        res = supabase.table("users").select("*").eq("username", username).eq("password", password).execute()
        if res.data and len(res.data) > 0:
            user = res.data[0]
            # بازیابی شناسه/نام اختصاصی باشگاه کاربر
            club_id = user.get("club_id", username)
            return True, club_id
        return False, ""
    except Exception as e:
        st.error(f"خطا در احراز هویت: {e}")
        return False, ""

def add_user(username, password, club_name=None, role="admin", *args, **kwargs):
    """ثبت نام مدیر جدید و اختصاص نام مجزای باشگاه"""
    try:
        # اگر نام باشگاه جداگانه وارد شده باشد از آن استفاده می‌شود، در غیر این صورت نام کاربری جایگزین می‌شود
        club_id = club_name.strip() if club_name and club_name.strip() else username.strip()

        data = {
            "username": username.strip(),
            "password": password.strip(),
            "role": role,
            "club_id": club_id
        }
        res = supabase.table("users").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در ساخت حساب (احتمالاً نام کاربری تکراری است): {e}")
        return False