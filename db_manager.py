import psycopg2
import pandas as pd
import streamlit as st
import sys
from datetime import datetime, date
from supabase import create_client, Client

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# --- ۱. اتصال به Supabase Client (جهت استفاده در auth.py و ai_analytics.py) ---
def init_supabase():
    url = st.secrets.get("SUPABASE_URL") or st.secrets.get("supabase", {}).get("url", "")
    key = st.secrets.get("SUPABASE_KEY") or st.secrets.get("supabase", {}).get("key", "")
    if not url or not key:
        return None
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception:
    supabase = None

# --- ۲. اتصال مستقیم PostgreSQL ---
def get_connection():
    db_config = st.secrets.get("postgres", {
        "host": st.secrets.get("DB_HOST", "db.xxxxxxxx.supabase.co"),
        "database": st.secrets.get("DB_NAME", "postgres"),
        "user": st.secrets.get("DB_USER", "postgres"),
        "password": st.secrets.get("DB_PASSWORD", ""),
        "port": int(st.secrets.get("DB_PORT", 5432))
    })
    
    return psycopg2.connect(
        host=db_config["host"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
        port=db_config["port"]
    )

# --- ۳. توابع اصلی فراخوانی‌شده توسط app.py ---

def add_member(full_name, phone, national_id, club_id, subscription_days=0):
    """ثبت عضو جدید در دیتابیس"""
    conn = get_connection()
    cursor = conn.cursor()
    
    parts = full_name.strip().split(' ', 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ''
    
    cursor.execute("""
        SELECT national_id, phone_number 
        FROM public.members 
        WHERE (national_id = %s OR phone_number = %s) AND club_id = %s
    """, (national_id, phone, club_id))
    
    existing = cursor.fetchone()
    if existing:
        conn.close()
        if existing[0] == national_id:
            return False, "خطا: عضوی با این کد ملی قبلاً ثبت شده است!"
        else:
            return False, "خطا: عضوی با این شماره تماس قبلاً ثبت شده است!"
            
    try:
        cursor.execute("""
            INSERT INTO public.members (first_name, last_name, national_id, phone_number, club_id) 
            VALUES (%s, %s, %s, %s, %s)
            RETURNING member_id
        """, (first_name, last_name, national_id, phone, club_id))
        
        member_id = cursor.fetchone()[0]
        
        if subscription_days > 0:
            cursor.execute("""
                INSERT INTO public.subscriptions 
                (member_id, remaining_sessions, start_date, end_date, status, club_id)
                VALUES (%s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '30 days', 'ACTIVE', %s)
            """, (member_id, subscription_days, club_id))
            
        conn.commit()
        conn.close()
        return True, f"عضو جدید '{full_name}' با موفقیت ثبت شد."
    except Exception as e:
        conn.close()
        return False, f"خطا در ثبت عضو: {e}"

def get_all_members(club_id):
    """دریافت لیست تمامی اعضای باشگاه همراه با اطلاعات آخرین اشتراک"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE public.subscriptions 
        SET status = 'EXPIRED' 
        WHERE end_date < CURRENT_DATE AND status = 'ACTIVE' AND club_id = %s
    """, (club_id,))
    conn.commit()
    
    query = """
        SELECT 
            m.member_id,
            m.full_name,
            m.national_id,
            m.phone_number,
            m.join_date,
            COALESCE(s.remaining_sessions, 0) AS remaining_sessions
        FROM public.members m
        LEFT JOIN (
            SELECT member_id, remaining_sessions,
                   ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY subscription_id DESC) as rn
            FROM public.subscriptions
            WHERE club_id = %s AND status = 'ACTIVE'
        ) s ON m.member_id = s.member_id AND s.rn = 1
        WHERE m.club_id = %s
        ORDER BY m.member_id DESC
    """
    
    cursor.execute(query, (club_id, club_id))
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "name": r[1] if r[1] else "",
            "national_id": r[2] if r[2] else "",
            "phone": r[3] if r[3] else "",
            "join_date": r[4].isoformat() if r[4] else None,
            "subscription_days": r[5]
        })
        
    return result

def update_subscription(member_id, sessions_to_add, club_id, overwrite=True):
    """تخصیص یا به روزرسانی بسته برای عضو"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        if overwrite:
            cursor.execute("""
                UPDATE public.subscriptions 
                SET status = 'EXPIRED' 
                WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE'
            """, (member_id, club_id))
            
        cursor.execute("""
            INSERT INTO public.subscriptions 
            (member_id, remaining_sessions, start_date, end_date, status, club_id)
            VALUES (%s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '30 days', 'ACTIVE', %s)
        """, (member_id, sessions_to_add, club_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in update_subscription: {e}")
        conn.close()
        return False

def decrement_subscription(member_id, club_id):
    """کسر یک جلسه از اشتراک فعال عضو"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT subscription_id, remaining_sessions 
            FROM public.subscriptions 
            WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE' AND remaining_sessions > 0
            ORDER BY subscription_id DESC
            LIMIT 1
        """, (member_id, club_id))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
            
        sub_id, rem_sessions = row
        new_rem = rem_sessions - 1
        new_status = 'EXPIRED' if new_rem <= 0 else 'ACTIVE'
        
        cursor.execute("""
            UPDATE public.subscriptions 
            SET remaining_sessions = %s, status = %s 
            WHERE subscription_id = %s
        """, (new_rem, new_status, sub_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in decrement_subscription: {e}")
        conn.close()
        return False

def clear_member_subscription(member_id, club_id):
    """صفر کردن اشتراک فعال کاربر"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE public.subscriptions 
            SET remaining_sessions = 0, status = 'EXPIRED' 
            WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE'
        """, (member_id, club_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in clear_member_subscription: {e}")
        conn.close()
        return False

def delete_member(member_id, club_id):
    """حذف کامل عضو از سیستم"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM public.members WHERE member_id = %s AND club_id = %s", (member_id, club_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in delete_member: {e}")
        conn.close()
        return False

def record_attendance(member_id, club_id):
    """ثبت تردد کاربر در جدول checkins"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT subscription_id 
            FROM public.subscriptions 
            WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE'
            ORDER BY subscription_id DESC 
            LIMIT 1
        """, (member_id, club_id))
        
        row = cursor.fetchone()
        sub_id = row[0] if row else None
        
        cursor.execute("""
            INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
            VALUES (%s, %s, NOW(), %s)
        """, (member_id, sub_id, club_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in record_attendance: {e}")
        conn.close()
        return False

def get_attendance_logs(club_id):
    """دریافت لیست ترددها"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT member_id, checkin_time 
        FROM public.checkins 
        WHERE club_id = %s 
        ORDER BY checkin_time DESC
    """, (club_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for r in rows:
        logs.append({
            "member_id": r[0],
            "check_in_time": r[1].isoformat() if r[1] else None
        })
        
    return logs

def reset_club_data(club_id):
    """حذف کلیه اطلاعات مربوط به یک باشگاه"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM public.checkins WHERE club_id = %s", (club_id,))
        cursor.execute("DELETE FROM public.ai_analytics WHERE club_id = %s", (club_id,))
        cursor.execute("DELETE FROM public.subscriptions WHERE club_id = %s", (club_id,))
        cursor.execute("DELETE FROM public.members WHERE club_id = %s", (club_id,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in reset_club_data: {e}")
        conn.close()
        return False