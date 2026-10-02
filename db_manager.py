import psycopg2
import pandas as pd
import streamlit as st
import sys
from datetime import datetime, date
from zoneinfo import ZoneInfo
from supabase import create_client, Client

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# --- ۱. اتصال به Supabase Client ---
def init_supabase():
    supabase_secrets = st.secrets.get("supabase", {})
    
    url = (
        st.secrets.get("SUPABASE_URL") or 
        supabase_secrets.get("url") or 
        supabase_secrets.get("SUPABASE_URL", "")
    )
    
    key = (
        st.secrets.get("SUPABASE_KEY") or 
        supabase_secrets.get("key") or 
        supabase_secrets.get("SUPABASE_KEY", "")
    )
    
    if not url or not key:
        return None
        
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    print(f"Error initializing Supabase client: {e}")
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
        port=db_config["port"],
        sslmode="require"
    )

# --- ۳. توابع اصلی مدیریت اعضا و دیتابیس ---

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
    """دریافت کلیه اعضا همراه با اطلاعات آخرین اشتراک"""
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
            COALESCE(s.remaining_sessions, 0) AS remaining_sessions,
            COALESCE(s.subscription_id::text, '-') AS subscription_id,
            COALESCE(s.end_date::text, '-') AS end_date,
            COALESCE(s.status, 'EXPIRED') AS status
        FROM public.members m
        LEFT JOIN (
            SELECT member_id, subscription_id, remaining_sessions, end_date, status,
                   ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY subscription_id DESC) as rn
            FROM public.subscriptions
            WHERE club_id = %s
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
            "subscription_days": r[5],
            "subscription_id": r[6],
            "end_date": r[7],
            "status": r[8]
        })
        
    return result

def get_active_members(club_id):
    """دریافت فقط اعضایی که دارای اشتراک ACTIVE هستند"""
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
            s.remaining_sessions,
            s.subscription_id,
            s.end_date
        FROM public.members m
        INNER JOIN (
            SELECT member_id, subscription_id, remaining_sessions, end_date,
                   ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY subscription_id DESC) as rn
            FROM public.subscriptions
            WHERE club_id = %s AND status = 'ACTIVE' AND end_date >= CURRENT_DATE
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
            "subscription_days": r[5],
            "subscription_id": r[6],
            "end_date": r[7].isoformat() if r[7] else None,
            "status": "ACTIVE"
        })
        
    return result

def update_subscription(member_id, sessions_to_add, club_id, overwrite=True):
    """تخصیص یا به‌روزرسانی بسته برای عضو"""
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
    """کسر یک جلسه از اشتراک فعال"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT subscription_id, remaining_sessions 
            FROM public.subscriptions 
            WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE'
            ORDER BY subscription_id DESC
            LIMIT 1
        """, (member_id, club_id))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
            
        sub_id, rem_sessions = row
        new_rem = max(0, rem_sessions - 1)
        
        cursor.execute("""
            UPDATE public.subscriptions 
            SET remaining_sessions = %s 
            WHERE subscription_id = %s
        """, (new_rem, sub_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in decrement_subscription: {e}")
        conn.close()
        return False

def clear_member_subscription(member_id, club_id):
    """صفر کردن اشتراک فعال کاربر و تغییر وضعیت به EXPIRED"""
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
    """ثبت تردد کاربر در جدول checkins بر اساس تایم‌زون دقیق ایران"""
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
        
        # استفاده از زمان صریح ایران با ZoneInfo
        tehran_now = datetime.now(ZoneInfo("Asia/Tehran"))
        
        cursor.execute("""
            INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
            VALUES (%s, %s, %s, %s)
        """, (member_id, sub_id, tehran_now, club_id))
        
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
    """حذف کلیه اطلاعات مربوط به یک باشگاه و ریست هوشمند شمارنده شناسه (Identity Sequence)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM public.checkins WHERE club_id = %s;", (club_id,))
        cursor.execute("DELETE FROM public.ai_analytics WHERE club_id = %s;", (club_id,))
        cursor.execute("DELETE FROM public.subscriptions WHERE club_id = %s;", (club_id,))
        cursor.execute("DELETE FROM public.members WHERE club_id = %s;", (club_id,))
        
        reset_sequence_query = """
        DO $$
        DECLARE
            seq_members text;
            max_m_id bigint;
            seq_subs text;
            max_s_id bigint;
            seq_checkins text;
            max_c_id bigint;
        BEGIN
            seq_members := pg_get_serial_sequence('public.members', 'member_id');
            IF seq_members IS NOT NULL THEN
                SELECT MAX(member_id) INTO max_m_id FROM public.members;
                IF max_m_id IS NULL THEN
                    PERFORM setval(seq_members, 1, false);
                ELSE
                    PERFORM setval(seq_members, max_m_id, true);
                END IF;
            END IF;

            seq_subs := pg_get_serial_sequence('public.subscriptions', 'subscription_id');
            IF seq_subs IS NOT NULL THEN
                SELECT MAX(subscription_id) INTO max_s_id FROM public.subscriptions;
                IF max_s_id IS NULL THEN
                    PERFORM setval(seq_subs, 1, false);
                ELSE
                    PERFORM setval(seq_subs, max_s_id, true);
                END IF;
            END IF;

            seq_checkins := pg_get_serial_sequence('public.checkins', 'checkin_id');
            IF seq_checkins IS NOT NULL THEN
                SELECT MAX(checkin_id) INTO max_c_id FROM public.checkins;
                IF max_c_id IS NULL THEN
                    PERFORM setval(seq_checkins, 1, false);
                ELSE
                    PERFORM setval(seq_checkins, max_c_id, true);
                END IF;
            END IF;
        END $$;
        """
        
        cursor.execute(reset_sequence_query)
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in reset_club_data: {e}")
        conn.close()
        return False