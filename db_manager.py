import os
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# -------------------------------------------------------------
# تنظیم و دریافت کلیدهای اتصال به Supabase
# -------------------------------------------------------------
SUPABASE_URL = None
SUPABASE_KEY = None

try:
    if "SUPABASE_URL" in st.secrets:
        SUPABASE_URL = st.secrets["SUPABASE_URL"]
    if "SUPABASE_KEY" in st.secrets:
        SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    pass

if not SUPABASE_URL:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
if not SUPABASE_KEY:
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"خطا در ایجاد اتصال Supabase: {e}")
else:
    st.error("⚠️ کلیدهای اتصال به Supabase (SUPABASE_URL و SUPABASE_KEY) یافت نشدند.")


def add_member(name, phone, national_id, club_id, subscription_days=0):
    """ثبت عضو جدید بدون بسته اولیه و بررسی یکتایی کد ملی"""
    if not supabase:
        return False, "اتصال به دیتابیس برقرار نیست."
    try:
        sub_count = int(subscription_days)
        data = {
            "name": name.strip(),
            "phone": phone.strip(),
            "national_id": national_id.strip(),
            "subscription_days": sub_count,
            "status": "active" if sub_count > 0 else "inactive",
            "join_date": datetime.now().date().isoformat(),
            "club_id": club_id
        }
        res = supabase.table("members").insert(data).execute()
        return True, "عضو جدید با موفقیت ثبت شد."
    except Exception as e:
        err_msg = str(e).lower()
        if any(term in err_msg for term in ["duplicate", "unique", "23505", "already exists"]):
            return False, "⚠️ این کد ملی قبلاً برای این باشگاه ثبت شده است."
        return False, f"خطا در ثبت عضو: {e}"


def get_all_members(club_id):
    """دریافت لیست تمامی اعضای یک باشگاه مشخص"""
    if not supabase:
        return []
    try:
        res = supabase.table("members").select("*").eq("club_id", club_id).order("id", desc=True).execute()
        return res.data if res.data else []
    except Exception as e:
        st.error(f"خطا در دریافت لیست اعضا: {e}")
        return []


def search_member(search_query, club_id):
    """جستجوی جامع عضو بر اساس نام، کد ملی، شماره تماس یا کد عضویت"""
    if not supabase:
        return []
    try:
        res = supabase.table("members").select("*").eq("club_id", club_id).execute()
        data = res.data if res.data else []
        query = search_query.strip().lower()
        
        filtered = [
            m for m in data 
            if query in str(m.get("name", "") or "").lower() 
            or query in str(m.get("national_id", "") or "")
            or query in str(m.get("phone", "") or "")
            or query in str(m.get("id", "") or "")
        ]
        return filtered
    except Exception as e:
        st.error(f"خطا در جستجو: {e}")
        return []


def update_subscription(member_id, sessions, club_id, overwrite=True):
    """ثبت یا تمدید بسته/جلسات برای ورزشکار و بروزرسانی تاریخ شروع به امروز"""
    if not supabase:
        return False
    try:
        today_str = datetime.now().date().isoformat()
        
        if overwrite:
            new_sessions = int(sessions)
        else:
            res = supabase.table("members").select("subscription_days").eq("id", member_id).eq("club_id", club_id).execute()
            current_sessions = (res.data[0].get("subscription_days", 0) or 0) if res.data else 0
            new_sessions = current_sessions + int(sessions)

        new_status = "active" if new_sessions > 0 else "expired"

        update_res = supabase.table("members").update({
            "subscription_days": new_sessions,
            "join_date": today_str,
            "status": new_status
        }).eq("id", member_id).eq("club_id", club_id).execute()
        
        return bool(update_res.data)
    except Exception as e:
        st.error(f"خطا در تمدید اشتراک: {e}")
        return False


def decrement_subscription(member_id, club_id):
    """کسر یک جلسه از ورزشکار پس از ثبت ورود"""
    if not supabase:
        return False
    try:
        res = supabase.table("members").select("subscription_days").eq("id", member_id).eq("club_id", club_id).execute()
        if not res.data:
            return False
        
        current_sub = res.data[0].get("subscription_days", 0) or 0
        new_sub = max(0, current_sub - 1)
        new_status = "active" if new_sub > 0 else "expired"

        update_res = supabase.table("members").update({
            "subscription_days": new_sub,
            "status": new_status
        }).eq("id", member_id).eq("club_id", club_id).execute()
        
        return bool(update_res.data)
    except Exception as e:
        st.error(f"خطا در کسر جلسه: {e}")
        return False


def clear_member_subscription(member_id, club_id):
    """صفر کردن اشتراک عضو بدون حذف حساب کاربری"""
    if not supabase:
        return False
    try:
        res = supabase.table("members").update({
            "subscription_days": 0,
            "status": "expired"
        }).eq("id", member_id).eq("club_id", club_id).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در صفر کردن اشتراک: {e}")
        return False


def record_attendance(member_id, club_id):
    """ثبت تاریخچه تردد (ورود) ورزشکار"""
    if not supabase:
        return False
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
    if not supabase:
        return []
    try:
        res = supabase.table("attendance").select("*, members(name, phone)").eq("club_id", club_id).order("check_in_time", desc=True).execute()
        return res.data if res.data else []
    except Exception as e:
        st.error(f"خطا در دریافت سوابق تردد: {e}")
        return []


def delete_member(member_id, club_id):
    """حذف کامل عضو به همراه کلیه سوابق تردد مرتبط (جلوگیری از خطای کلید خارجی)"""
    if not supabase:
        return False
    try:
        # ۱. ابتدا حذف ترددهای عضو از جدول attendance
        supabase.table("attendance").delete().eq("member_id", member_id).eq("club_id", club_id).execute()
        # ۲. سپس حذف عضو از جدول members
        res = supabase.table("members").delete().eq("id", member_id).eq("club_id", club_id).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"خطا در حذف عضو: {e}")
        return False


def reset_club_data(club_id):
    """حذف تمامی اعضا و ترددهای مربوط به یک باشگاه مشخص"""
    if not supabase:
        return False
    try:
        supabase.table("attendance").delete().eq("club_id", club_id).execute()
        supabase.table("members").delete().eq("club_id", club_id).execute()
        return True
    except Exception as e:
        st.error(f"خطا در پاکسازی دیتابیس: {e}")
        return False