import psycopg2
import pandas as pd
import streamlit as st
import re
import sys
import threading
import time
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

# --- ۲. اتصال مستقیم PostgreSQL (با استخر اتصال) ---
#
# چرا استخر؟ ساختن یک اتصال تازه به Supabase (TCP + TLS + احراز هویت) معمولاً چند صد میلی‌ثانیه تا بیش از یک ثانیه
# طول می‌کشد و هر کلیک در برنامه ۳ تا ۴ query می‌زند. قبلاً برای هر query یک اتصال تازه ساخته می‌شد (مجموعاً چند ثانیه).
# حالا اتصال‌های آزاد نگه داشته و دوباره استفاده می‌شوند؛ بقیه کد دست‌نخورده است: همچنان
# conn = get_connection() ... conn.close() می‌نویسند، فقط close() اتصال را «به استخر برمی‌گرداند».
#
# ایمنی:
#  - هر اتصال فقط در اختیار یک تابع است (استخر فقط اتصال‌های «آزاد» را نگه می‌دارد، نه اشتراکی)
#  - موقع برگرداندن، تراکنش نیمه‌کاره rollback می‌شود
#  - اتصالی که مدتی بی‌استفاده بوده قبل از استفاده با یک SELECT 1 سنجیده می‌شود و در صورت مرده‌بودن دور ریخته می‌شود
#  - اگر تابعی conn.close() را فراموش کند، هنگام آزادشدن شیء اتصال دور ریخته می‌شود (نشتی ایجاد نمی‌شود)
def _db_config():
    return st.secrets.get("postgres", {
        "host": st.secrets.get("DB_HOST", "db.xxxxxxxx.supabase.co"),
        "database": st.secrets.get("DB_NAME", "postgres"),
        "user": st.secrets.get("DB_USER", "postgres"),
        "password": st.secrets.get("DB_PASSWORD", ""),
        "port": int(st.secrets.get("DB_PORT", 5432))
    })


def _new_raw_connection():
    """ساخت یک اتصال تازه (کند). keepalive از قطع‌شدن بی‌صدای اتصال‌های آزاد جلوگیری می‌کند."""
    db_config = _db_config()
    return psycopg2.connect(
        host=db_config["host"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
        port=db_config["port"],
        sslmode="require",
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )


class _PooledConnection:
    """اتصال قرضی از استخر: مثل اتصال psycopg2 رفتار می‌کند، فقط close() آن را به استخر برمی‌گرداند"""

    def __init__(self, raw, pool):
        self._raw = raw
        self._pool = pool
        self._released = False

    def cursor(self, *args, **kwargs):
        return self._raw.cursor(*args, **kwargs)

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        self._pool.release(self)

    @property
    def autocommit(self):
        return self._raw.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._raw.autocommit = value

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._raw, name)

    def __del__(self):
        try:
            if not self._released:
                self._pool.release(self, discard=True)
        except Exception:
            pass


class _ConnectionPool:
    """استخر ساده و thread-safe از اتصال‌های آزاد (برای اتصال‌های در حال استفاده سقف نمی‌گذارد)"""

    def __init__(self, connect, max_idle=4, stale_after=25.0):
        self._connect = connect
        self._max_idle = max_idle
        self._stale_after = stale_after
        self._idle = []                     # [(raw, آخرین زمان استفاده)]
        self._lock = threading.Lock()

    @staticmethod
    def _close_quietly(raw):
        try:
            raw.close()
        except Exception:
            pass

    def _is_usable(self, raw, last_used):
        try:
            if raw.closed:
                return False
            if time.monotonic() - last_used > self._stale_after:    # مدتی بی‌استفاده: قبل از استفاده بسنج
                cursor = raw.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                raw.rollback()
            return True
        except Exception:
            return False

    def acquire(self):
        while True:
            with self._lock:
                item = self._idle.pop() if self._idle else None          # آخرین استفاده‌شده اول (گرم‌ترین اتصال)
            if item is None:
                break
            raw, last_used = item
            if self._is_usable(raw, last_used):
                return _PooledConnection(raw, self)
            self._close_quietly(raw)
        return _PooledConnection(self._connect(), self)

    def release(self, wrapper, discard=False):
        if wrapper._released:
            return
        wrapper._released = True
        raw = wrapper._raw
        if discard:
            self._close_quietly(raw)
            return
        try:
            if raw.closed:
                return
            raw.rollback()                                               # تراکنش نیمه‌کاره پاک شود
        except Exception:
            self._close_quietly(raw)
            return
        with self._lock:
            if len(self._idle) < self._max_idle:
                self._idle.append((raw, time.monotonic()))
                return
        self._close_quietly(raw)

    def idle_count(self):
        with self._lock:
            return len(self._idle)


_POOL = _ConnectionPool(_new_raw_connection)


def get_connection():
    """یک اتصال از استخر می‌دهد (اگر آزاد نبود، اتصال تازه می‌سازد). مثل قبل با conn.close() برگردانده می‌شود."""
    return _POOL.acquire()


def describe_endpoint(host, port):
    """
    نوع اتصال را از روی آدرس و پورت تشخیص می‌دهد (بدون نمایش آدرس یا نام پروژه):
    {"kind": "pooler"|"direct"|"other", "mode": توضیح فارسی, "region": منطقه سرور Supabase یا None}
    """
    host, port = str(host or ""), int(port or 0)
    if ".pooler.supabase.com" in host:
        m = re.search(r"aws-\d+-([a-z0-9-]+)\.pooler\.supabase\.com", host)
        mode = {6543: "Transaction pooler (پورت ۶۵۴۳)", 5432: "Session pooler (پورت ۵۴۳۲)"}.get(port, f"Pooler (پورت {port})")
        return {"kind": "pooler", "mode": mode, "region": m.group(1) if m else None}
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return {"kind": "direct", "mode": f"اتصال مستقیم (پورت {port})", "region": None}
    return {"kind": "other", "mode": f"سرور دیگر (پورت {port})", "region": None}


def measure_db_speed(samples=3):
    """
    اندازه‌گیری سرعت دیتابیس برای عیب‌یابی (میلی‌ثانیه):
      new_connection_ms : ساخت یک اتصال تازه (همان چیزی که قبلاً برای هر query پرداخت می‌شد)
      roundtrip_ms      : رفت‌وبرگشت یک query ساده روی اتصال آماده (هزینه واقعی هر query)
      pool_checkout_ms  : گرفتن اتصال از استخر (باید نزدیک صفر باشد)
    """
    config = _db_config()
    info = describe_endpoint(config.get("host"), config.get("port"))

    started = time.perf_counter()
    raw = _new_raw_connection()
    new_ms = (time.perf_counter() - started) * 1000
    try:
        cursor = raw.cursor()
        times = []
        for _ in range(samples):
            started = time.perf_counter()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            times.append((time.perf_counter() - started) * 1000)
        raw.rollback()
    finally:
        raw.close()

    warm = get_connection()          # اگر استخر خالی باشد همین‌جا ساخته می‌شود؛ بعد از اولین بار آماده است
    warm.close()
    started = time.perf_counter()
    conn = get_connection()
    conn.close()
    checkout_ms = (time.perf_counter() - started) * 1000

    return {**info, "new_connection_ms": new_ms, "roundtrip_ms": sorted(times)[len(times) // 2],
            "pool_checkout_ms": checkout_ms}


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


# ---------------------------------------------------------------
# آرشیو اعضا: تشخیص خودکار وجود ستون members.archived_at
# اگر SQL مهاجرت هنوز اجرا نشده باشد، برنامه مثل قبل کار می‌کند (فقط قابلیت آرشیو غیرفعال است).
# ---------------------------------------------------------------
_ARCHIVE_STATE = {"ok": None, "checked_at": 0.0}
_ARCHIVE_RECHECK_SECONDS = 30


def archive_supported(force=False):
    """
    آیا ستون members.archived_at در دیتابیس وجود دارد؟
    نتیجه مثبت برای همیشه (تا ری‌استارت برنامه) ذخیره می‌شود؛ نتیجه منفی فقط ۳۰ ثانیه،
    تا بعد از اجرای SQL مهاجرت نیازی به ری‌استارت نباشد.
    """
    now = time.monotonic()
    if _ARCHIVE_STATE["ok"] is True:
        return True
    if not force and _ARCHIVE_STATE["ok"] is False and now - _ARCHIVE_STATE["checked_at"] < _ARCHIVE_RECHECK_SECONDS:
        return False
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'members' AND column_name = 'archived_at'
            """)
            ok = cursor.fetchone() is not None
        finally:
            conn.close()
    except Exception as e:
        print(f"Error in archive_supported: {e}")
        return False
    _ARCHIVE_STATE["ok"] = ok
    _ARCHIVE_STATE["checked_at"] = now
    return ok


def _not_archived(alias="m"):
    """قطعه SQL برای حذف اعضای آرشیوشده از نتایج (اگر آرشیو فعال نباشد، رشته خالی)"""
    if not archive_supported():
        return ""
    prefix = f"{alias}." if alias else ""
    return f" AND {prefix}archived_at IS NULL"


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

        archived_col = ", archived_at" if archive_supported() else ""
        cursor.execute(f"""
            SELECT national_id, phone_number{archived_col}
            FROM public.members
            WHERE (national_id = %s OR phone_number = %s) AND club_id = %s
        """, (national_id, phone, club_id))

        found = cursor.fetchall()
        if found:
            live = [r for r in found if not (archived_col and r[2] is not None)]
            if not live:
                return False, "این عضو قبلاً ثبت و آرشیو شده است؛ از «مدیریت و حذف ← آرشیو» بازگردانی‌اش کنید."
            existing = live[0]
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
    
    query = f"""
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
        WHERE m.club_id = %s{_not_archived()}
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
    
    query = f"""
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
        WHERE m.club_id = %s{_not_archived()}
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
    """حذف دائمی یک عضو همراه با اشتراک‌ها و ترددهایش (در یک تراکنش). فقط برای سازگاری با کد قبلی؛ نسخه کامل: delete_members_permanently"""
    return bool(delete_members_permanently([member_id], club_id).get("ok"))

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
            "SELECT member_id FROM public.members WHERE member_id = %s AND club_id = %s" + _not_archived("") + " FOR UPDATE",
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


def get_checkin_times(club_id):
    """زمان همه ترددهای باشگاه (datetime آگاه از منطقه زمانی) برای نمودارهای صفحه آمار"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT checkin_time
            FROM public.checkins
            WHERE club_id = %s AND checkin_time IS NOT NULL
        """, (club_id,))
        return [r[0] for r in cursor.fetchall()]
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


# ---------------------------------------------------------------
# مدیریت و حذف: آرشیو، حذف دائمی، ابطال اشتراک، پشتیبان‌گیری
# همه عملیات تغییردهنده «اتمیک» هستند و همیشه با club_id محدود می‌شوند.
# ---------------------------------------------------------------
def _clean_ids(member_ids):
    """فهرست شناسه‌ها را به اعداد صحیح یکتا تبدیل می‌کند (مقادیر نامعتبر نادیده گرفته می‌شوند)"""
    ids = set()
    for value in member_ids or []:
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(ids)


def get_members_impact(member_ids, club_id):
    """تعداد اشتراک‌ها و ترددهایی که همراه این اعضا حذف می‌شوند: {subscriptions, checkins}"""
    ids = _clean_ids(member_ids)
    if not ids:
        return {"subscriptions": 0, "checkins": 0}
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM public.subscriptions WHERE member_id = ANY(%s) AND club_id = %s", (ids, club_id))
        subscriptions = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM public.checkins WHERE member_id = ANY(%s) AND club_id = %s", (ids, club_id))
        checkins = cursor.fetchone()[0]
        return {"subscriptions": int(subscriptions), "checkins": int(checkins)}
    finally:
        conn.close()


def archive_members(member_ids, club_id):
    """
    آرشیو اعضا: از فهرست‌ها و آمار فعال کنار می‌روند ولی اشتراک‌ها و ترددهایشان حفظ می‌شود (قابل بازگردانی).
    خروجی: {"ok": True, "count"} یا {"ok": False, "code", "message"}
    """
    ids = _clean_ids(member_ids)
    if not ids:
        return _fail("EMPTY", "عضوی انتخاب نشده است.")
    if not archive_supported():
        return _fail("NO_ARCHIVE", "قابلیت آرشیو هنوز در دیتابیس فعال نشده است. فایل SQL مهاجرت را یک‌بار اجرا کنید.")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE public.members SET archived_at = now()
            WHERE member_id = ANY(%s) AND club_id = %s AND archived_at IS NULL
        """, (ids, club_id))
        count = cursor.rowcount
        conn.commit()
        if count == 0:
            return _fail("NOT_FOUND", "عضو پیدا نشد یا قبلاً آرشیو شده است.")
        return {"ok": True, "count": count}
    except Exception as e:
        print(f"Error in archive_members: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در آرشیو عضو. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def restore_members(member_ids, club_id):
    """بازگردانی اعضای آرشیوشده به فهرست‌ها. خروجی: {"ok": True, "count"} یا {"ok": False, ...}"""
    ids = _clean_ids(member_ids)
    if not ids:
        return _fail("EMPTY", "عضوی انتخاب نشده است.")
    if not archive_supported():
        return _fail("NO_ARCHIVE", "قابلیت آرشیو هنوز در دیتابیس فعال نشده است.")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE public.members SET archived_at = NULL
            WHERE member_id = ANY(%s) AND club_id = %s AND archived_at IS NOT NULL
        """, (ids, club_id))
        count = cursor.rowcount
        conn.commit()
        if count == 0:
            return _fail("NOT_FOUND", "عضو در آرشیو پیدا نشد (شاید قبلاً بازگردانده شده است).")
        return {"ok": True, "count": count}
    except Exception as e:
        print(f"Error in restore_members: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در بازگردانی عضو. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def delete_members_permanently(member_ids, club_id):
    """
    حذف دائمی اعضا همراه با ترددها، اشتراک‌ها و سوابق تحلیلی‌شان، همه در «یک تراکنش»
    (یا همه پاک می‌شود یا هیچ‌چیز؛ نیازی به ON DELETE CASCADE در دیتابیس نیست).
    خروجی: {"ok": True, "members", "subscriptions", "checkins"} یا {"ok": False, "code", "message"}
    """
    ids = _clean_ids(member_ids)
    if not ids:
        return _fail("EMPTY", "عضوی انتخاب نشده است.")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT member_id FROM public.members WHERE member_id = ANY(%s) AND club_id = %s FOR UPDATE",
            (ids, club_id))
        found = [r[0] for r in cursor.fetchall()]
        if not found:
            conn.rollback()
            return _fail("NOT_FOUND", "عضو پیدا نشد (شاید قبلاً حذف شده است).")

        cursor.execute("""
            DELETE FROM public.checkins
            WHERE club_id = %s
              AND (member_id = ANY(%s)
                   OR subscription_id IN (
                       SELECT subscription_id FROM public.subscriptions WHERE member_id = ANY(%s) AND club_id = %s))
        """, (club_id, found, found, club_id))
        checkins_deleted = cursor.rowcount

        cursor.execute("DELETE FROM public.ai_analytics WHERE member_id = ANY(%s) AND club_id = %s", (found, club_id))

        cursor.execute("DELETE FROM public.subscriptions WHERE member_id = ANY(%s) AND club_id = %s", (found, club_id))
        subscriptions_deleted = cursor.rowcount

        cursor.execute("DELETE FROM public.members WHERE member_id = ANY(%s) AND club_id = %s", (found, club_id))
        members_deleted = cursor.rowcount

        conn.commit()
        return {"ok": True, "members": members_deleted, "subscriptions": subscriptions_deleted,
                "checkins": checkins_deleted}
    except Exception as e:
        print(f"Error in delete_members_permanently: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در حذف عضو؛ هیچ داده‌ای پاک نشد. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def cancel_subscription(member_id, club_id):
    """
    ابطال اشتراک فعال عضو: جلسات باقی‌مانده صفر و وضعیت EXPIRED می‌شود (ترددهای قبلی دست‌نخورده می‌ماند).
    مقدار قبلی برگردانده می‌شود تا بشود ابطال را لغو کرد (restore_subscription).
    خروجی: {"ok": True, "cancelled": [{"subscription_id", "remaining"}], "burned"} یا {"ok": False, ...}
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT subscription_id, remaining_sessions
            FROM public.subscriptions
            WHERE member_id = %s AND club_id = %s AND status = 'ACTIVE'
            ORDER BY subscription_id DESC
            FOR UPDATE
        """, (member_id, club_id))
        rows = cursor.fetchall()
        if not rows:
            conn.rollback()
            return _fail("NO_ACTIVE", "این عضو اشتراک فعالی ندارد.")

        cancelled = [{"subscription_id": r[0], "remaining": int(r[1] or 0)} for r in rows]
        cursor.execute("""
            UPDATE public.subscriptions
            SET remaining_sessions = 0, status = 'EXPIRED'
            WHERE subscription_id = ANY(%s) AND club_id = %s
        """, ([c["subscription_id"] for c in cancelled], club_id))
        conn.commit()
        return {"ok": True, "cancelled": cancelled, "burned": sum(c["remaining"] for c in cancelled)}
    except Exception as e:
        print(f"Error in cancel_subscription: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در ابطال اشتراک. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def restore_subscription(items, club_id):
    """
    لغو ابطال اشتراک: اشتراک‌های ابطال‌شده با همان تعداد جلسه قبلی دوباره فعال می‌شوند (در یک تراکنش).
    items: [{"subscription_id", "remaining"}] (خروجی cancel_subscription)
    اگر اشتراک تاریخ‌گذشته شده یا بعد از آن اشتراک جدیدی برای عضو ثبت شده باشد، بازگردانی انجام نمی‌شود.
    """
    if not items:
        return _fail("EMPTY", "اشتراکی برای بازگردانی نیست.")
    try:
        parsed = [(int(i["subscription_id"]), int(i["remaining"])) for i in items]
    except (KeyError, TypeError, ValueError):
        return _fail("EMPTY", "اطلاعات اشتراک نامعتبر است.")
    all_ids = [sid for sid, _ in parsed]

    conn = get_connection()
    try:
        cursor = conn.cursor()
        for sid, remaining in parsed:
            cursor.execute("""
                SELECT member_id, status, (end_date < CURRENT_DATE) AS is_past
                FROM public.subscriptions
                WHERE subscription_id = %s AND club_id = %s
                FOR UPDATE
            """, (sid, club_id))
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return _fail("NOT_FOUND", "این اشتراک پیدا نشد.")
            member_id, status, is_past = row
            if status == "ACTIVE":
                conn.rollback()
                return _fail("ALREADY", "این اشتراک قبلاً دوباره فعال شده است.")
            if is_past:
                conn.rollback()
                return _fail("PAST", "مهلت اعتبار این اشتراک تمام شده است؛ بازگرداندن ممکن نیست.")

            cursor.execute("""
                SELECT 1 FROM public.subscriptions
                WHERE member_id = %s AND club_id = %s AND subscription_id > %s AND NOT (subscription_id = ANY(%s))
                LIMIT 1
            """, (member_id, club_id, sid, all_ids))
            if cursor.fetchone():
                conn.rollback()
                return _fail("NEWER", "بعد از این اشتراک، اشتراک جدیدی برای عضو ثبت شده است؛ بازگرداندن ممکن نیست.")

            cursor.execute("""
                UPDATE public.subscriptions SET remaining_sessions = %s, status = 'ACTIVE'
                WHERE subscription_id = %s AND club_id = %s
            """, (remaining, sid, club_id))

        conn.commit()
        return {"ok": True, "remaining": sum(r for _, r in parsed)}
    except Exception as e:
        print(f"Error in restore_subscription: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return _fail("ERROR", "خطا در بازگردانی اشتراک. چند لحظه بعد دوباره تلاش کنید.")
    finally:
        conn.close()


def get_archived_members(club_id):
    """
    اعضای آرشیوشده (جدیدترین آرشیو اول) همراه با تعداد اشتراک‌ها و ترددهای حفظ‌شده:
    [{id, name, national_id, phone, join_date, archived_at, subscriptions, checkins}]
    اگر قابلیت آرشیو فعال نباشد، فهرست خالی برمی‌گردد.
    """
    if not archive_supported():
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.member_id, m.full_name, m.national_id, m.phone_number, m.join_date, m.archived_at,
                   (SELECT COUNT(*) FROM public.subscriptions s WHERE s.member_id = m.member_id) AS subs,
                   (SELECT COUNT(*) FROM public.checkins c WHERE c.member_id = m.member_id) AS checks
            FROM public.members m
            WHERE m.club_id = %s AND m.archived_at IS NOT NULL
            ORDER BY m.archived_at DESC, m.member_id DESC
        """, (club_id,))
        return [{
            "id": r[0],
            "name": r[1] or "",
            "national_id": r[2] or "",
            "phone": r[3] or "",
            "join_date": r[4].isoformat() if hasattr(r[4], "isoformat") else (str(r[4]) if r[4] else None),
            "archived_at": r[5],
            "subscriptions": int(r[6]),
            "checkins": int(r[7]),
        } for r in cursor.fetchall()]
    finally:
        conn.close()


def get_club_counts(club_id):
    """تعداد کل داده‌های باشگاه (شامل اعضای آرشیوشده): {members, subscriptions, checkins, analytics}"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM public.members WHERE club_id = %s),
                (SELECT COUNT(*) FROM public.subscriptions WHERE club_id = %s),
                (SELECT COUNT(*) FROM public.checkins WHERE club_id = %s),
                (SELECT COUNT(*) FROM public.ai_analytics WHERE club_id = %s)
        """, (club_id, club_id, club_id, club_id))
        r = cursor.fetchone()
        return {"members": int(r[0]), "subscriptions": int(r[1]), "checkins": int(r[2]), "analytics": int(r[3])}
    finally:
        conn.close()


_BACKUP_QUERIES = {
    "members": "SELECT * FROM public.members WHERE club_id = %s ORDER BY member_id",
    "subscriptions": "SELECT * FROM public.subscriptions WHERE club_id = %s ORDER BY subscription_id",
    "checkins": "SELECT * FROM public.checkins WHERE club_id = %s ORDER BY checkin_id",
    "ai_analytics": "SELECT * FROM public.ai_analytics WHERE club_id = %s ORDER BY analytics_id",
}


def export_club_backup(club_id):
    """داده‌های خام باشگاه برای نسخه پشتیبان: {نام جدول: (ستون‌ها, ردیف‌ها)}. رمز عبور کاربران شامل نمی‌شود."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        tables = {}
        for name, query in _BACKUP_QUERIES.items():
            cursor.execute(query, (club_id,))
            columns = [d[0] for d in cursor.description]
            tables[name] = (columns, cursor.fetchall())
        return tables
    finally:
        conn.close()
