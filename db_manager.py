import psycopg2
import pandas as pd
import streamlit as st
import sys
from datetime import datetime, date, timedelta, timezone
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

_TO_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _normalize_digits(value):
    """ارقام فارسی/عربی را به لاتین تبدیل و فاصله‌های اطراف را حذف می‌کند (None بدون تغییر می‌ماند)"""
    if value is None:
        return None
    return str(value).translate(_TO_LATIN_DIGITS).strip()


def _duplicate_member_message(error):
    """
    اگر خطا نقض قید یکتایی دیتابیس باشد (مثلاً دو ثبت‌نام هم‌زمان با کد ملی یکسان)،
    پیام فارسی مناسب برمی‌گرداند؛ در غیر این صورت None.
    """
    text = str(error).lower()
    constraint = (getattr(getattr(error, "diag", None), "constraint_name", None) or "").lower()
    is_unique = getattr(error, "pgcode", None) == "23505" or "duplicate key" in text or "unique constraint" in text
    if not is_unique:
        return None
    hint = constraint + " " + text
    if "national_id" in hint:
        return "خطا: عضوی با این کد ملی قبلاً ثبت شده است!"
    if "phone" in hint:
        return "خطا: عضوی با این شماره تماس قبلاً ثبت شده است!"
    return "خطا: عضوی با این مشخصات قبلاً ثبت شده است!"


def add_member(full_name, phone, national_id, club_id, subscription_days=0, first_name=None, last_name=None):
    """
    ثبت عضو جدید در دیتابیس.
    اگر first_name و last_name جداگانه داده شوند همان‌ها ذخیره می‌شوند (نام‌های دوبخشی مثل «محمد رضا» درست ثبت می‌شوند).
    در غیر این صورت full_name با اولین فاصله به نام و نام خانوادگی شکسته می‌شود (رفتار قبلی).
    کد ملی و شماره تماس قبل از ذخیره به ارقام لاتین تبدیل می‌شوند تا قید یکتایی دیتابیس دور زده نشود.
    """
    national_id = _normalize_digits(national_id)
    phone = _normalize_digits(phone)

    conn = get_connection()

    try:
        cursor = conn.cursor()

        if first_name is not None:
            first_name = first_name.strip()
            last_name = (last_name or '').strip()
        else:
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
            if national_id and existing[0] == national_id:
                return False, "خطا: عضوی با این کد ملی قبلاً ثبت شده است!"
            return False, "خطا: عضوی با این شماره تماس قبلاً ثبت شده است!"

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
        return True, f"عضو جدید '{full_name}' با موفقیت ثبت شد."
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        friendly = _duplicate_member_message(e)
        if friendly:
            return False, friendly
        return False, f"خطا در ثبت عضو: {e}"
    finally:
        conn.close()


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
        join_dt = r[4].isoformat() if hasattr(r[4], 'isoformat') else str(r[4]) if r[4] else None
        result.append({
            "id": r[0],
            "name": r[1] if r[1] else "",
            "national_id": r[2] if r[2] else "",
            "phone": r[3] if r[3] else "",
            "join_date": join_dt,
            "subscription_days": r[5],
            "subscription_id": str(r[6]),
            "end_date": str(r[7]),
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
        join_dt = r[4].isoformat() if hasattr(r[4], 'isoformat') else str(r[4]) if r[4] else None
        end_dt = r[7].isoformat() if hasattr(r[7], 'isoformat') else str(r[7]) if r[7] else None
        result.append({
            "id": r[0],
            "name": r[1] if r[1] else "",
            "national_id": r[2] if r[2] else "",
            "phone": r[3] if r[3] else "",
            "join_date": join_dt,
            "subscription_days": r[5],
            "subscription_id": str(r[6]),
            "end_date": end_dt,
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
    """دریافت لیست ترددها با پشتیبانی ایمن از انواع داده زمان"""
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
        c_time = r[1]
        if c_time is not None:
            if hasattr(c_time, 'isoformat'):
                c_time_str = c_time.isoformat()
            else:
                c_time_str = str(c_time)
        else:
            c_time_str = None

        logs.append({
            "member_id": r[0],
            "check_in_time": c_time_str
        })
        
    return logs

# ---------------------------------------------------------------
# ثبت ورود (تردد): عملیات «اتمیک» و پشتیبان صفحه ثبت ورود
# ---------------------------------------------------------------
def _fail(code, message):
    return {"ok": False, "code": code, "message": message}


def check_in_member(member_id, club_id):
    """
    ثبت ورود و کسر یک جلسه در «یک تراکنش» (یا هر دو انجام می‌شود یا هیچ‌کدام).
    ردیف اشتراک قفل می‌شود تا دو دستگاه هم‌زمان نتوانند دوبار جلسه کم کنند.
    خروجی: {"ok": True, "remaining", "checkin_id", "checkin_time"}  یا  {"ok": False, "code", "message"}
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT subscription_id, remaining_sessions, (end_date < CURRENT_DATE) AS is_expired
            FROM public.subscriptions
            WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE'
            ORDER BY subscription_id DESC
            LIMIT 1
            FOR UPDATE
        """, (member_id, club_id))
        row = cursor.fetchone()

        if not row:
            conn.rollback()
            return _fail("NO_ACTIVE", "این عضو اشتراک فعالی ندارد.")
        sub_id, remaining, is_expired = row
        if is_expired:
            conn.rollback()
            return _fail("EXPIRED", "اشتراک این عضو منقضی شده است.")
        if remaining is None or remaining <= 0:
            conn.rollback()
            return _fail("NO_SESSIONS", "جلسات این عضو تمام شده است.")

        cursor.execute("""
            UPDATE public.subscriptions
            SET remaining_sessions = remaining_sessions - 1
            WHERE subscription_id = %s
            RETURNING remaining_sessions
        """, (sub_id,))
        new_remaining = cursor.fetchone()[0]

        tehran_now = datetime.now(ZoneInfo("Asia/Tehran"))
        cursor.execute("""
            INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
            VALUES (%s, %s, %s, %s)
            RETURNING checkin_id
        """, (member_id, sub_id, tehran_now, club_id))
        checkin_id = cursor.fetchone()[0]

        conn.commit()
        return {"ok": True, "remaining": new_remaining, "checkin_id": checkin_id, "checkin_time": tehran_now}
    except Exception as e:
        print(f"Error in check_in_member: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در ثبت ورود. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def _as_aware(value):
    """مقدار زمان (datetime یا رشته ISO) را به datetime آگاه از منطقه زمانی تبدیل می‌کند"""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def undo_checkin(checkin_id, club_id, max_minutes=10):
    """
    لغو یک ورود اشتباه: ردیف تردد حذف و یک جلسه به اشتراک برمی‌گردد (در یک تراکنش).
    فقط تا max_minutes دقیقه بعد از ثبت و تا زمانی که اشتراک آن ورود هنوز فعال است مجاز است.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT subscription_id, checkin_time
            FROM public.checkins
            WHERE checkin_id = %s AND club_id = %s
            FOR UPDATE
        """, (checkin_id, club_id))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return _fail("NOT_FOUND", "این ورود پیدا نشد یا قبلاً لغو شده است.")

        sub_id, checkin_time = row
        age = datetime.now(timezone.utc) - _as_aware(checkin_time)
        if age > timedelta(minutes=max_minutes):
            conn.rollback()
            return _fail("TOO_OLD", f"فقط تا {max_minutes} دقیقه بعد از ثبت می‌توان ورود را لغو کرد.")

        remaining = None
        if sub_id is not None:
            cursor.execute("""
                UPDATE public.subscriptions
                SET remaining_sessions = remaining_sessions + 1
                WHERE subscription_id = %s AND club_id = %s AND status = 'ACTIVE'
                RETURNING remaining_sessions
            """, (sub_id, club_id))
            updated = cursor.fetchone()
            if not updated:
                conn.rollback()
                return _fail("NOT_ACTIVE", "اشتراک مربوط به این ورود دیگر فعال نیست؛ لغو ممکن نیست.")
            remaining = updated[0]

        cursor.execute("DELETE FROM public.checkins WHERE checkin_id = %s AND club_id = %s", (checkin_id, club_id))
        conn.commit()
        return {"ok": True, "remaining": remaining}
    except Exception as e:
        print(f"Error in undo_checkin: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در لغو ورود. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def get_today_checkins(club_id):
    """ترددهای امروز (بر اساس روز تهران) از جدید به قدیم: [{checkin_id, member_id, checkin_time}]"""
    day_start = datetime.now(ZoneInfo("Asia/Tehran")).replace(hour=0, minute=0, second=0, microsecond=0)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT checkin_id, member_id, checkin_time
            FROM public.checkins
            WHERE club_id = %s AND checkin_time >= %s
            ORDER BY checkin_time DESC
        """, (club_id, day_start))
        return [{"checkin_id": r[0], "member_id": r[1], "checkin_time": r[2]} for r in cursor.fetchall()]
    finally:
        conn.close()


def get_last_checkins(club_id):
    """آخرین زمان تردد هر عضو: {member_id: datetime}"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT member_id, MAX(checkin_time)
            FROM public.checkins
            WHERE club_id = %s AND member_id IS NOT NULL
            GROUP BY member_id
        """, (club_id,))
        return {r[0]: r[1] for r in cursor.fetchall()}
    finally:
        conn.close()


# ---------------------------------------------------------------
# تخصیص بسته: عملیات «اتمیک» و پشتیبان صفحه تخصیص بسته
# ---------------------------------------------------------------
def assign_package(member_id, club_id, sessions, validity_days=30):
    """
    تخصیص بسته جدید به عضو در «یک تراکنش».
    - ردیف عضو قفل می‌شود تا دو تخصیص هم‌زمان برای یک نفر دو اشتراک فعال نسازد.
    - اگر عضو هنوز اشتراک فعالِ دارای جلسه دارد، تخصیص انجام نمی‌شود (قانون: بعد از تمام شدن جلسات یا انقضا).
    - تاریخ شروع «امروزِ تهران» و پایان = شروع + validity_days است.
    خروجی: {"ok": True, "subscription_id", "sessions", "start_date", "end_date"} یا {"ok": False, "code", "message"}
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT member_id FROM public.members WHERE member_id = %s AND club_id = %s FOR UPDATE",
            (member_id, club_id),
        )
        if not cursor.fetchone():
            conn.rollback()
            return _fail("NOT_FOUND", "عضو پیدا نشد.")

        cursor.execute("""
            SELECT subscription_id, remaining_sessions, (end_date < CURRENT_DATE) AS is_expired
            FROM public.subscriptions
            WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE'
            ORDER BY subscription_id DESC
            LIMIT 1
        """, (member_id, club_id))
        row = cursor.fetchone()
        if row and row[1] is not None and row[1] > 0 and not row[2]:
            conn.rollback()
            return _fail("HAS_ACTIVE", "این عضو هنوز اشتراک فعال و دارای جلسه دارد؛ بعد از تمام شدن جلسات یا انقضا می‌توان بسته جدید ثبت کرد.")

        cursor.execute("""
            UPDATE public.subscriptions SET status = 'EXPIRED'
            WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE'
        """, (member_id, club_id))

        start_date = datetime.now(ZoneInfo("Asia/Tehran")).date()
        end_date = start_date + timedelta(days=validity_days)
        cursor.execute("""
            INSERT INTO public.subscriptions
            (member_id, remaining_sessions, start_date, end_date, status, club_id)
            VALUES (%s, %s, %s, %s, 'ACTIVE', %s)
            RETURNING subscription_id
        """, (member_id, sessions, start_date, end_date, club_id))
        subscription_id = cursor.fetchone()[0]

        conn.commit()
        return {"ok": True, "subscription_id": subscription_id, "sessions": sessions,
                "start_date": start_date, "end_date": end_date}
    except Exception as e:
        print(f"Error in assign_package: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در ثبت بسته. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def undo_assignment(subscription_id, club_id, max_minutes=10):
    """
    لغو تخصیص اشتباه: اشتراک تازه حذف می‌شود (در یک تراکنش).
    فقط تا max_minutes دقیقه بعد از ثبت و فقط اگر هنوز هیچ ورودی از آن اشتراک ثبت نشده باشد.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT created_at
            FROM public.subscriptions
            WHERE subscription_id = %s AND club_id = %s
            FOR UPDATE
        """, (subscription_id, club_id))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return _fail("NOT_FOUND", "این اشتراک پیدا نشد یا قبلاً لغو شده است.")

        created_at = row[0]
        if created_at is None or datetime.now(timezone.utc) - _as_aware(created_at) > timedelta(minutes=max_minutes):
            conn.rollback()
            return _fail("TOO_OLD", f"فقط تا {max_minutes} دقیقه بعد از ثبت می‌توان تخصیص را لغو کرد.")

        cursor.execute("SELECT COUNT(*) FROM public.checkins WHERE subscription_id = %s", (subscription_id,))
        if cursor.fetchone()[0] > 0:
            conn.rollback()
            return _fail("USED", "از این اشتراک ورود ثبت شده است؛ لغو ممکن نیست.")

        cursor.execute("DELETE FROM public.subscriptions WHERE subscription_id = %s AND club_id = %s", (subscription_id, club_id))
        conn.commit()
        return {"ok": True}
    except Exception as e:
        print(f"Error in undo_assignment: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در لغو تخصیص. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def get_member_subscriptions(member_id, club_id, limit=3):
    """
    تاریخچه اشتراک‌های یک عضو (جدید به قدیم) همراه با تعداد جلسه‌های مصرف‌شده:
    [{subscription_id, remaining, start_date, end_date, status, used}]
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.subscription_id, s.remaining_sessions, s.start_date, s.end_date, s.status,
                   COALESCE(c.used, 0) AS used
            FROM public.subscriptions s
            LEFT JOIN (
                SELECT subscription_id, COUNT(*) AS used
                FROM public.checkins
                WHERE club_id = %s
                GROUP BY subscription_id
            ) c ON c.subscription_id = s.subscription_id
            WHERE s.member_id = %s AND s.club_id = %s
            ORDER BY s.subscription_id DESC
            LIMIT %s
        """, (club_id, member_id, club_id, limit))
        return [{"subscription_id": r[0], "remaining": r[1], "start_date": r[2], "end_date": r[3],
                 "status": r[4], "used": r[5]} for r in cursor.fetchall()]
    finally:
        conn.close()


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