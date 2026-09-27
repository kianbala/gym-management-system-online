import os
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = None
SUPABASE_KEY = None

try:
    SUPABASE_URL = st.secrets.get("SUPABASE_URL")
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
except Exception:
    pass

if not SUPABASE_URL:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
if not SUPABASE_KEY:
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ۱. مدیریت اعضا ---
def add_member(name, phone, national_id, subscription_days, sessions_left, club_id):
    """ثبت عضو جدید همراه با روزها و تعداد جلسات اولیه"""
    try:
        data = {
            "name": name.strip(),
            "phone": phone.strip(),
            "national_id": national_id.strip(),
            "subscription_days": int(subscription_days),
            "sessions_left": int(sessions_left),
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
    """دریافت لیست اعضای یک باشگاه"""
    try:
        res = supabase.table("members").select("*").eq("club_id", club_id).order("id", desc=True).execute()
        return res.data if res.data else []
    except Exception as e:
        st.error(f"خطا در دریافت لیست اعضا: {e}")
        return []

def search_member(search_query, club_id):
    """جستجوی عضو بر اساس نام یا کد ملی"""
    try:
        res = supabase.table("members").select("*").eq("club_id", club_id).execute()
        data = res.data if res.data else []
        query = search_query.strip().lower()
        return [
            m for m in data 
            if query in m.get("name", "").lower() or query in m.get("national_id", "")
        ]
    except Exception as e:
        st.error(f"خطا در جستجو: {e}")
        return []

def delete_member(member_id, club_id):
    """حذف عضو و سوابق تردد"""
    try:
        supabase.table("attendance").delete().eq("member_id", member_id).eq("club_id", club_id).execute()
        res = supabase.table("members").delete().eq("id", member_id).eq("club_id", club_id).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در حذف عضو: {e}")
        return False

# --- ۲. مدیریت بسته‌ها ---
def add_package(title, sessions, duration_days, price, club_id):
    """ثبت تعریف بسته جدید"""
    try:
        data = {
            "title": title.strip(),
            "sessions": int(sessions),
            "duration_days": int(duration_days),
            "price": float(price),
            "club_id": club_id
        }
        res = supabase.table("packages").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در ایجاد بسته: {e}")
        return False

def get_all_packages(club_id):
    """دریافت بسته‌های فعال باشگاه"""
    try:
        res = supabase.table("packages").select("*").eq("club_id", club_id).execute()
        return res.data if res.data else []
    except Exception as e:
        st.error(f"خطا در دریافت بسته‌ها: {e}")
        return []

def assign_package_to_member(member_id, package_id, club_id):
    """تخصیص بسته به عضو (افزایش جلسات و روزهای اعتبار)"""
    try:
        pkg_res = supabase.table("packages").select("*").eq("id", package_id).eq("club_id", club_id).execute()
        mem_res = supabase.table("members").select("*").eq("id", member_id).eq("club_id", club_id).execute()
        
        if not pkg_res.data or not mem_res.data:
            return False
            
        pkg = pkg_res.data[0]
        mem = mem_res.data[0]

        new_days = mem.get("subscription_days", 0) + pkg["duration_days"]
        new_sessions = mem.get("sessions_left", 0) + pkg["sessions"]

        update_res = supabase.table("members").update({
            "subscription_days": new_days,
            "sessions_left": new_sessions,
            "status": "active"
        }).eq("id", member_id).eq("club_id", club_id).execute()

        return bool(update_res.data)
    except Exception as e:
        st.error(f"خطا در تخصیص بسته: {e}")
        return False

# --- ۳. مدیریت تردد ---
def record_attendance(member_id, club_id):
    """ثبت ورود و کسر یک جلسه از حساب عضو"""
    try:
        mem_res = supabase.table("members").select("sessions_left").eq("id", member_id).eq("club_id", club_id).execute()
        if not mem_res.data:
            return False, "عضو یافت نشد."

        sessions = mem_res.data[0].get("sessions_left", 0)
        if sessions <= 0:
            return False, "تعداد جلسات عضو به پایان رسیده است!"

        # کسر جلسه
        supabase.table("members").update({"sessions_left": sessions - 1}).eq("id", member_id).eq("club_id", club_id).execute()
        
        # ثبت ورود
        data = {
            "member_id": member_id,
            "check_in_time": datetime.now().isoformat(),
            "club_id": club_id
        }
        res = supabase.table("attendance").insert(data).execute()
        return True, "ورود با موفقیت ثبت شد و ۱ جلسه کسر گردید."
    except Exception as e:
        return False, f"خطا در ثبت تردد: {e}"