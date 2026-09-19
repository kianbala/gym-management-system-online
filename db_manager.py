import os
from datetime import datetime
import pandas as pd
import streamlit as st
from supabase import create_client, Client

# خواندن کلیدها از Secrets استریم‌لیت یا فایل .env محلی
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def add_member(name, phone, national_id, subscription_days, club_id):
    """ثبت عضو جدید در جدول members با شناسه باشگاه"""
    try:
        data = {
            "name": name.strip(),
            "phone": phone.strip(),
            "national_id": national_id.strip(),
            "subscription_days": int(subscription_days),
            "status": "active",
            "join_date": datetime.now().date().isoformat(),
            "club_id": club_id
        }
        res = supabase.table("members").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در ثبت عضو: {e}")
        return False


def get_all_members(club_id):
    """دریافت لیست تمامی اعضای یک باشگاه مشخص"""
    try:
        res = supabase.table("members").select("*").eq("club_id", club_id).execute()
        return res.data if res.data else []
    except Exception as e:
        st.error(f"خطا در دریافت لیست اعضا: {e}")
        return []


def search_member(search_query, club_id):
    """جستجوی عضو بر اساس نام یا کد ملی در باشگاه مشخص"""
    try:
        res = supabase.table("members").select("*").eq("club_id", club_id).execute()
        data = res.data if res.data else []
        query = search_query.strip().lower()
        
        filtered = [
            m for m in data 
            if query in m.get("name", "").lower() or query in m.get("national_id", "")
        ]
        return filtered
    except Exception as e:
        st.error(f"خطا در جستجو: {e}")
        return []


def update_subscription(member_id, add_days, club_id):
    """افزایش تعداد روزهای اعتبار اشتراک عضو"""
    try:
        # ۱. دریافت اطلاعات فعلی کاربر
        res = supabase.table("members").select("subscription_days").eq("id", member_id).eq("club_id", club_id).execute()
        if not res.data:
            return False
        
        current_days = res.data[0].get("subscription_days", 0)
        new_days = current_days + int(add_days)

        # ۲. به‌روزرسانی روزها و فعال‌سازی مجدد
        update_res = supabase.table("members").update({
            "subscription_days": new_days,
            "status": "active"
        }).eq("id", member_id).eq("club_id", club_id).execute()
        
        return bool(update_res.data)
    except Exception as e:
        st.error(f"خطا در تمدید اشتراک: {e}")
        return False


def record_attendance(member_id, club_id):
    """ثبت تاریخچه تردد (ورود) ورزشکار"""
    try:
        data = {
            "member_id": member_id,
            "check_in_time": datetime.now().isoformat(),
            "club_id": club_id
        }
        res = supabase.table("attendance").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در ثبت تردد: {e}")
        return False


def get_attendance_logs(club_id):
    """دریافت سوابق تردد اعضای باشگاه"""
    try:
        res = supabase.table("attendance").select("*, members(name, phone)").eq("club_id", club_id).order("check_in_time", desc=True).execute()
        return res.data if res.data else []
    except Exception as e:
        st.error(f"خطا در دریافت سوابق تردد: {e}")
        return []


def delete_member(member_id, club_id):
    """حذف کامل عضو و سوابق تردد مرتبط از باشگاه"""
    try:
        # حذف ترددها
        supabase.table("attendance").delete().eq("member_id", member_id).eq("club_id", club_id).execute()
        # حذف خود عضو
        res = supabase.table("members").delete().eq("id", member_id).eq("club_id", club_id).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در حذف عضو: {e}")
        return False