import psycopg2
import pandas as pd
import sys
from datetime import datetime, date
import streamlit as st

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# --- تنظیمات اتصال به Supabase PostgreSQL ---
def get_connection():
    db_config = st.secrets.get("postgres", {
        "host": "db.xxxxxxxxxxxx.supabase.co",
        "database": "postgres",
        "user": "postgres",
        "password": "YOUR_PASSWORD",
        "port": 5432
    })
    
    return psycopg2.connect(
        host=db_config["host"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
        port=db_config["port"]
    )

# --- ۱. تابع جستجوی اعضای دارای اشتراک فعال جهت ثبت ورود ---
def search_members_for_checkin(club_id, search_term=""):
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
            s.subscription_id, 
            m.full_name, 
            m.phone_number, 
            m.national_id, 
            s.remaining_sessions, 
            s.end_date
        FROM public.subscriptions s
        JOIN public.members m ON s.member_id = m.member_id
        WHERE s.status = 'ACTIVE' AND s.remaining_sessions > 0 AND s.club_id = %s
    """
    
    params = [club_id]
    if search_term and search_term.strip():
        query += " AND (m.full_name ILIKE %s OR m.phone_number ILIKE %s OR m.national_id ILIKE %s)"
        term = f"%{search_term.strip()}%"
        params.extend([term, term, term])
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        result.append({
            'member_id': r[0],
            'subscription_id': r[1],
            'full_name': r[2],
            'phone_number': r[3],
            'national_id': r[4],
            'remaining_sessions': r[5],
            'end_date': r[6]
        })
    return result

# --- ۲. تابع افزودن عضو جدید ---
def add_member(club_id, first_name, last_name, national_id, phone_number):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT national_id, phone_number 
        FROM public.members 
        WHERE (national_id = %s OR phone_number = %s) AND club_id = %s
    """, (national_id, phone_number, club_id))
    
    existing_member = cursor.fetchone()
    
    if existing_member:
        conn.close()
        if existing_member[0] == national_id:
            return False, "خطا: عضوی با این کد ملی قبلاً ثبت شده است!"
        else:
            return False, "خطا: عضوی با این شماره تماس قبلاً ثبت شده است!"
            
    try:
        cursor.execute(
            "INSERT INTO public.members (first_name, last_name, national_id, phone_number, club_id) VALUES (%s, %s, %s, %s, %s)", 
            (first_name, last_name, national_id, phone_number, club_id)
        )
        conn.commit()
        conn.close()
        return True, f"عضو جدید '{first_name} {last_name}' با موفقیت ثبت شد."
    except Exception as e:
        conn.close()
        return False, f"خطا در ثبت عضو: {e}"

# --- ۳. تابع حذف عضو ---
def delete_member(club_id, member_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT member_id FROM public.members WHERE member_id = %s AND club_id = %s", (member_id, club_id))
    if not cursor.fetchone():
        conn.close()
        return False, f"خطا: عضوی با کد عضویت {member_id} یافت نشد!"

    try:
        cursor.execute("DELETE FROM public.members WHERE member_id = %s AND club_id = %s", (member_id, club_id))
        conn.commit()
        conn.close()
        return True, f"عضو شماره {member_id} و تمامی سوابق مربوطه با موفقیت حذف شدند."
    except Exception as e:
        conn.close()
        return False, f"خطا در حذف عضو: {e}"

# --- ۴. تابع اختصاص بسته ---
def assign_package(club_id, member_id, package_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT member_id FROM public.members WHERE member_id = %s AND club_id = %s", (member_id, club_id))
    if not cursor.fetchone():
        conn.close()
        return False, f"خطا: عضوی با کد {member_id} وجود ندارد!"

    cursor.execute("""
        SELECT subscription_id, remaining_sessions, end_date 
        FROM public.subscriptions 
        WHERE member_id = %s AND status = 'ACTIVE' AND club_id = %s
        ORDER BY subscription_id DESC
        LIMIT 1
    """, (member_id, club_id))
    active_sub = cursor.fetchone()
    
    today = date.today()
    
    if active_sub:
        sub_id, remaining_sessions, end_date = active_sub
        
        if isinstance(end_date, str):
            try:
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").date()
        elif isinstance(end_date, datetime):
            end_date = end_date.date()
            
        if remaining_sessions > 0 and (end_date and end_date >= today):
            conn.close()
            return False, f"این کاربر هنوز {remaining_sessions} جلسه فعال دارد و تاریخ اشتراکش تمام نشده است!"
        else:
            cursor.execute("UPDATE public.subscriptions SET status = 'EXPIRED' WHERE member_id = %s AND status = 'ACTIVE' AND club_id = %s", (member_id, club_id))
    
    cursor.execute("SELECT total_sessions, validity_days FROM public.packages WHERE package_id = %s AND club_id = %s", (package_id, club_id))
    pkg = cursor.fetchone()
    
    if pkg:
        total_sessions, validity_days = pkg
        query = """
            INSERT INTO public.subscriptions (member_id, package_id, remaining_sessions, start_date, end_date, status, club_id)
            VALUES (%s, %s, %s, CURRENT_DATE, CURRENT_DATE + (%s || ' days')::INTERVAL, 'ACTIVE', %s)
        """
        cursor.execute(query, (member_id, package_id, total_sessions, validity_days, club_id))
        conn.commit()
        conn.close()
        return True, "اشتراک جدید با موفقیت فعال شد."
    else:
        conn.close()
        return False, "بسته مورد نظر یافت نشد."

# --- ۵. تابع ثبت ورود ---
def record_checkin(club_id, member_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE public.subscriptions 
        SET status = 'EXPIRED' 
        WHERE end_date < CURRENT_DATE AND status = 'ACTIVE' AND club_id = %s
    """, (club_id,))
    conn.commit()

    cursor.execute("""
        SELECT subscription_id, remaining_sessions 
        FROM public.subscriptions 
        WHERE member_id = %s AND status = 'ACTIVE' AND remaining_sessions > 0 AND club_id = %s
        ORDER BY subscription_id DESC
        LIMIT 1
    """, (member_id, club_id))
    
    active_sub = cursor.fetchone()
    
    if not active_sub:
        conn.close()
        return False, "❌ کاربر اشتراک فعال یا جلسه باقی‌مانده ندارد!"
    
    sub_id, remaining_sessions = active_sub
    
    cursor.execute("""
        INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
        VALUES (%s, %s, NOW(), %s)
    """, (member_id, sub_id, club_id))
    
    new_remaining = remaining_sessions - 1
    
    if new_remaining == 0:
        cursor.execute("""
            UPDATE public.subscriptions 
            SET remaining_sessions = %s, status = 'EXPIRED' 
            WHERE subscription_id = %s AND club_id = %s
        """, (new_remaining, sub_id, club_id))
    else:
        cursor.execute("""
            UPDATE public.subscriptions 
            SET remaining_sessions = %s 
            WHERE subscription_id = %s AND club_id = %s
        """, (new_remaining, sub_id, club_id))
        
    conn.commit()
    conn.close()
    
    return True, f"✅ ورود ثبت شد. جلسات باقی‌مانده: {new_remaining} جلسه"

# --- ۶. تابع دریافت لیست اعضا ---
def get_active_members(club_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE public.subscriptions 
        SET status = 'EXPIRED' 
        WHERE end_date < CURRENT_DATE AND status = 'ACTIVE' AND club_id = %s
    """, (club_id,))
    conn.commit()
    
    query = """
        SELECT m.member_id, m.full_name, m.national_id, m.phone_number, s.subscription_id, s.remaining_sessions, s.end_date, s.status
        FROM public.members m
        LEFT JOIN public.subscriptions s ON m.member_id = s.member_id
        WHERE m.club_id = %s
    """
    df = pd.read_sql(query, conn, params=(club_id,))
    conn.close()
    return df

# --- ۷. تابع حذف اشتراک ---
def delete_subscription(club_id, subscription_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT subscription_id FROM public.subscriptions WHERE subscription_id = %s AND club_id = %s", (subscription_id, club_id))
    if not cursor.fetchone():
        conn.close()
        return False, "اشتراک مورد نظر یافت نشد."

    cursor.execute("DELETE FROM public.subscriptions WHERE subscription_id = %s AND club_id = %s", (subscription_id, club_id))
    conn.commit()
    conn.close()
    return True, f"اشتراک شماره {subscription_id} با موفقیت حذف شد."

# --- ۸. تابع دریافت کلیه بسته‌ها ---
def get_all_packages(club_id):
    conn = get_connection()
    query = "SELECT * FROM public.packages WHERE club_id = %s"
    df = pd.read_sql(query, conn, params=(club_id,))
    conn.close()
    return df

# --- ۹. تابع ریست کامل داده‌های باشگاه جاری ---
def reset_all_data(club_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM public.checkins WHERE club_id = %s;", (club_id,))
    cursor.execute("DELETE FROM public.ai_analytics WHERE club_id = %s;", (club_id,))
    cursor.execute("DELETE FROM public.subscriptions WHERE club_id = %s;", (club_id,))
    cursor.execute("DELETE FROM public.members WHERE club_id = %s;", (club_id,))
    
    conn.commit()
    conn.close()
    return True

# --- ۱۰. تابع جستجوی اعضا جهت تخصیص بسته ---
def search_all_members(club_id, search_term=""):
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
            m.phone_number, 
            m.national_id,
            s.remaining_sessions,
            s.end_date,
            s.status
        FROM public.members m
        LEFT JOIN (
            SELECT member_id, remaining_sessions, end_date, status,
                   ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY subscription_id DESC) as rn
            FROM public.subscriptions
            WHERE club_id = %s
        ) s ON m.member_id = s.member_id AND s.rn = 1
        WHERE m.club_id = %s
    """
    
    params = [club_id, club_id]
    if search_term and search_term.strip():
        query += " AND (m.full_name ILIKE %s OR m.phone_number ILIKE %s OR m.national_id ILIKE %s)"
        term = f"%{search_term.strip()}%"
        params.extend([term, term, term])
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    today = date.today()
    result = []
    
    for r in rows:
        member_id, full_name, phone, national_id, rem_sessions, end_date, status = r
        
        is_expired = False
        if end_date:
            if isinstance(end_date, str):
                try:
                    end_date_val = datetime.strptime(end_date, "%Y-%m-%d").date()
                except ValueError:
                    end_date_val = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").date()
            elif isinstance(end_date, datetime):
                end_date_val = end_date.date()
            else:
                end_date_val = end_date
                
            if end_date_val < today:
                is_expired = True

        if status == 'ACTIVE' and rem_sessions is not None and rem_sessions > 0 and not is_expired:
            can_assign = False
            status_text = f"🔴 دارای اشتراک فعال ({rem_sessions} جلسه باقی‌مانده)"
        else:
            can_assign = True
            if status is None:
                status_text = "🟢 مجاز به ثبت بسته (بدون اشتراک)"
            elif rem_sessions == 0:
                status_text = "🟢 مجاز به تمدید (اتمام جلسات)"
            else:
                status_text = "🟢 مجاز به تمدید (اشتراک منقضی شده)"

        result.append({
            'member_id': member_id,
            'full_name': full_name,
            'phone_number': phone,
            'national_id': national_id,
            'can_assign': can_assign,
            'status_text': status_text
        })
        
    return result

# --- ۱۱. تابع جستجوی داشبورد ---
def search_dashboard_members(club_id, search_term=""):
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
            COALESCE(p.title, 'بدون بسته') AS package_title,
            s.subscription_id,
            s.remaining_sessions,
            s.end_date,
            s.status,
            CASE 
                WHEN MAX(c.checkin_time) IS NOT NULL THEN 
                    CASE 
                        WHEN (CURRENT_DATE - MAX(c.checkin_time)::date) < 0 THEN 0
                        ELSE (CURRENT_DATE - MAX(c.checkin_time)::date)
                    END
                ELSE -1
            END AS days_absent
        FROM public.members m
        LEFT JOIN (
            SELECT member_id, package_id, subscription_id, remaining_sessions, end_date, status,
                   ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY subscription_id DESC) as rn
            FROM public.subscriptions
            WHERE club_id = %s
        ) s ON m.member_id = s.member_id AND s.rn = 1
        LEFT JOIN public.packages p ON s.package_id = p.package_id
        LEFT JOIN public.checkins c ON m.member_id = c.member_id
        WHERE m.club_id = %s
    """
    
    params = [club_id, club_id]
    
    if search_term and search_term.strip():
        query += " AND (m.full_name ILIKE %s OR m.phone_number ILIKE %s OR m.national_id ILIKE %s OR CAST(m.member_id AS TEXT) ILIKE %s)"
        term = f"%{search_term.strip()}%"
        params.extend([term, term, term, term])
        
    group_by_clause = """
        GROUP BY 
            m.member_id, 
            m.full_name, 
            m.national_id, 
            m.phone_number, 
            p.title, 
            s.subscription_id, 
            s.remaining_sessions, 
            s.end_date, 
            s.status
        ORDER BY m.member_id DESC
    """
    
    final_query = query + group_by_clause
    df = pd.read_sql(final_query, conn, params=params)
        
    conn.close()
    return df

# --- ۱۲. تابع گزارش تحلیل ریزش اعضا ---
def get_churn_analytics_report(club_id):
    conn = get_connection()
    query = """
        SELECT 
            m.member_id,
            m.full_name,
            a.churn_risk_score AS "نمره ریسک ریزش (۰ تا ۱۰۰)",
            a.last_calculated AS "آخرین محاسبه"
        FROM public.ai_analytics a
        JOIN public.members m ON a.member_id = m.member_id
        WHERE a.club_id = %s
        ORDER BY a.churn_risk_score DESC
    """
    df = pd.read_sql(query, conn, params=(club_id,))
    conn.close()
    return df

# --- توابع کمکی و سازگارکننده جهت هماهنگی کامل با app.py ---

def get_all_members(club_id):
    """جایگزین تابع دریافت همه اعضا جهت هماهنگی با app.py"""
    return get_active_members(club_id)

def update_subscription(arg1, arg2, arg3=None):
    """ویرایش جلسات باقی‌مانده یک اشتراک (سازگار با ۲ یا ۳ ورودی)"""
    conn = get_connection()
    cursor = conn.cursor()
    if arg3 is None:
        subscription_id, remaining_sessions = arg1, arg2
        cursor.execute("""
            UPDATE public.subscriptions 
            SET remaining_sessions = %s 
            WHERE subscription_id = %s
        """, (remaining_sessions, subscription_id))
    else:
        club_id, subscription_id, remaining_sessions = arg1, arg2, arg3
        cursor.execute("""
            UPDATE public.subscriptions 
            SET remaining_sessions = %s 
            WHERE subscription_id = %s AND club_id = %s
        """, (remaining_sessions, subscription_id, club_id))
    conn.commit()
    conn.close()
    return True

def decrement_subscription(arg1, arg2=None):
    """کم کردن یک جلسه از اشتراک کاربر (پشتیبانی از ۱ یا ۲ ورودی)"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if arg2 is None:
            sub_id = arg1
            cursor.execute("""
                UPDATE public.subscriptions 
                SET remaining_sessions = GREATEST(0, remaining_sessions - 1) 
                WHERE subscription_id = %s
            """, (sub_id,))
            cursor.execute("""
                UPDATE public.subscriptions 
                SET status = 'EXPIRED' 
                WHERE subscription_id = %s AND remaining_sessions = 0
            """, (sub_id,))
        else:
            club_id, sub_id = arg1, arg2
            cursor.execute("""
                UPDATE public.subscriptions 
                SET remaining_sessions = GREATEST(0, remaining_sessions - 1) 
                WHERE subscription_id = %s AND club_id = %s
            """, (sub_id, club_id))
            cursor.execute("""
                UPDATE public.subscriptions 
                SET status = 'EXPIRED' 
                WHERE subscription_id = %s AND club_id = %s AND remaining_sessions = 0
            """, (sub_id, club_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error decrementing subscription: {e}")
        return False
    finally:
        conn.close()