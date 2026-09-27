import os
from datetime import datetime
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


def add_member(name, phone, national_id, club_id, subscription_days=30):
    """ثبت عضو جدید با میزان اعتبار پیش‌فرض ۳۰ روز و بررسی یکتایی کد ملی"""
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
        return True, "عضو جدید با موفقیت ثبت شد."
    except Exception as e:
        err_msg = str(e)
        if "duplicate key" in err_msg or "unique constraint" in err_msg:
            return False, "⚠️ این کد ملی قبلاً برای این باشگاه ثبت شده است."
        return False, f"خطا در ثبت عضو: {e}"


def get_all_members(club_id):
    """دریافت لیست تمامی اعضای یک باشگاه مشخص"""
    try:
        res = supabase.table("members").select("*").eq("club_id", club_id).order("id", desc=True).execute()
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
        res = supabase.table("members").select("subscription_days").eq("id", member_id).eq("club_id", club_id).execute()
        if not res.data:
            return False
        
        current_days = res.data[0].get("subscription_days", 0) or 0
        new_days = current_days + int(add_days)

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
    """حذف عضو (ترددها به صورت خودکار توسط CASCADE حذف می‌شوند)"""
    try:
        res = supabase.table("members").delete().eq("id", member_id).eq("club_id", club_id).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در حذف عضو: {e}")
        return False