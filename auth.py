import streamlit as st
from db_manager import supabase

def authenticate_user(username, password, *args, **kwargs):
    """احراز هویت کاربر و بازگرداندن وضعیت لاگین و شناسه اختصاصی باشگاه"""
    try:
        res = supabase.table("users").select("*").eq("username", username).eq("password", password).execute()
        if res.data and len(res.data) > 0:
            user = res.data[0]
            # شناسه باشگاه همان نام کاربری کاربر است
            club_id = user.get("club_id", username)
            return True, club_id
        return False, ""
    except Exception as e:
        st.error(f"خطا در احراز هویت: {e}")
        return False, ""

def add_user(username, password, *args, **kwargs):
    """ثبت نام مدیر جدید و اختصاص شناسه باشگاه بر اساس نام کاربری"""
    try:
        # شناسه باشگاه دقیقاً برابر با نام کاربری قرار می‌گیرد
        club_id = username.strip()
        role = "admin"

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
