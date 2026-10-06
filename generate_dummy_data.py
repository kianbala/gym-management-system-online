import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from db_manager import get_connection

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

FIRST_NAMES = [
    'علی', 'محمد', 'امیر', 'حسین', 'مهدی', 'رضا', 'سروش', 'آرش', 'کامران', 'نوید',
    'سارا', 'نیلوفر', 'مریم', 'زهرا', 'پریسا', 'فاطمه', 'مهرنوش', 'کیانا', 'مینا', 'نرگس'
]

LAST_NAMES = [
    'رضایی', 'محمدی', 'احمدی', 'کریمی', 'حسینی', 'کاظمی', 'قاسمی', 'نوری', 'مرادی', 'ابراهیمی',
    'صادقی', 'حیدری', 'موسوی', 'نجفی', 'مظفری', 'شریفی', 'فراهانی', 'جعفری', 'اکبری', 'باقری'
]

def get_user_club_id(cursor, username):
    """بررسی وجود مدیر در پایگاه داده و استخراج شناسه باشگاه او"""
    try:
        cursor.execute(
            "SELECT club_id, id FROM public.users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s));", 
            (username,)
        )
        res = cursor.fetchone()
        if res:
            # اگر club_id مقدار داشت همان را برمی‌گرداند، در غیر این صورت id کاربر را استفاده می‌کند
            return res[0] if res[0] is not None else res[1]
    except Exception as e:
        print(f"⚠️ خطا در استعلام کاربر: {e}")
    
    return None

def generate_data(username):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ۱. بررسی وجود مدیر سیستم
        club_id = get_user_club_id(cursor, username)

        if club_id is None:
            print(f"\n❌ خطا: همچین شخصی وجود ندارد! (کاربری با نام کاربری '{username}' در پایگاه داده یافت نشد)")
            return

        print(f"\n✅ مدیر سیستم تأیید شد. شناسه باشگاه: '{club_id}'")
        print(f"⏳ در حال ساخت ۳۰ عضو نمونه و ثبت ترددهای مربوطه...")

        now = datetime.now(TEHRAN_TZ)
        
        peak_hours = [17, 18, 18, 19, 19, 19, 20, 20, 21]
        regular_hours = [8, 9, 10, 11, 14, 15, 16, 22]
        all_hours = peak_hours + regular_hours

        risk_profiles = ['high_risk'] * 6 + ['medium_risk'] * 6 + ['low_risk'] * 18
        random.shuffle(risk_profiles)

        added_count = 0
        total_checkins_added = 0

        while added_count < 30:
            risk_profile = risk_profiles[added_count]
            f_name = random.choice(FIRST_NAMES)
            l_name = random.choice(LAST_NAMES)
            
            national_id = f"{random.randint(1000000000, 9999999999)}"
            phone_number = f"0912{random.randint(1000000, 9999999)}"

            cursor.execute(
                "SELECT 1 FROM public.members WHERE (national_id = %s OR phone_number = %s) AND club_id = %s", 
                (national_id, phone_number, club_id)
            )
            if cursor.fetchone():
                continue

            # درج عضو
            cursor.execute("""
                INSERT INTO public.members (first_name, last_name, national_id, phone_number, club_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING member_id;
            """, (f_name, l_name, national_id, phone_number, club_id))
            
            member_id = cursor.fetchone()[0]
            total_sessions = random.choice([12, 24])
            
            # تنظیم پارامترهای ریسک
            if risk_profile == 'high_risk':
                last_checkin_days_ago = random.randint(9, 20)
                days_active = random.randint(last_checkin_days_ago + 1, 29)
                remaining = random.randint(0, 3)

            elif risk_profile == 'medium_risk':
                if total_sessions == 12:
                    remaining = random.randint(2, 5)
                    last_checkin_days_ago = random.randint(5, 7)
                else:
                    remaining = random.randint(13, 15)
                    last_checkin_days_ago = random.randint(3, 4)
                days_active = random.randint(last_checkin_days_ago + 1, 29)

            else:
                if total_sessions == 12:
                    remaining = random.randint(6, 11)
                    last_checkin_days_ago = random.randint(0, 3)
                else:
                    remaining = random.randint(16, 23)
                    last_checkin_days_ago = random.randint(0, 2)
                days_active = random.randint(last_checkin_days_ago + 1, 29)

            start_date = (now - timedelta(days=days_active)).date()
            end_date = start_date + timedelta(days=30)
            sub_status = 'ACTIVE'

            # درج اشتراک
            cursor.execute("""
                INSERT INTO public.subscriptions (member_id, remaining_sessions, start_date, end_date, status, club_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING subscription_id;
            """, (member_id, remaining, start_date, end_date, sub_status, club_id))

            sub_id = cursor.fetchone()[0]

            # درج ترددها
            used_sessions = total_sessions - remaining

            if used_sessions > 0:
                hour = random.choice(all_hours)
                minute = random.randint(0, 59)
                
                last_checkin_time = (now - timedelta(days=last_checkin_days_ago)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )

                cursor.execute("""
                    INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
                    VALUES (%s, %s, %s, %s);
                """, (member_id, sub_id, last_checkin_time, club_id))
                total_checkins_added += 1

                past_sessions_count = used_sessions - 1
                start_past_days = min(last_checkin_days_ago + 1, days_active)
                end_past_days = days_active

                for _ in range(past_sessions_count):
                    if start_past_days <= end_past_days:
                        past_days_ago = random.randint(start_past_days, end_past_days)
                    else:
                        past_days_ago = days_active
                        
                    past_hour = random.choice(all_hours)
                    past_minute = random.randint(0, 59)
                    
                    past_checkin_time = (now - timedelta(days=past_days_ago)).replace(
                        hour=past_hour, minute=past_minute, second=0, microsecond=0
                    )
                    
                    cursor.execute("""
                        INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
                        VALUES (%s, %s, %s, %s);
                    """, (member_id, sub_id, past_checkin_time, club_id))
                    total_checkins_added += 1

            added_count += 1

        conn.commit()
        print(f"✅ با موفقیت ۳۰ عضو و {total_checkins_added} رکورد تردد برای مدیر '{username}' (شناسه: {club_id}) ثبت شد.")

    except Exception as e:
        conn.rollback()
        print(f"❌ خطا در هنگام ثبت داده‌ها: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    username_input = input("لطفاً نام کاربری مدیر سیستم را وارد کنید: ").strip()
    while not username_input:
        username_input = input("نام کاربری نمی‌تواند خالی باشد: ").strip()
        
    generate_data(username_input)