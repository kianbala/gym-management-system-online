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

def generate_data(username_or_club):
    conn = get_connection()
    cursor = conn.cursor()

    # پیدا کردن شناسه باشگاه
    cursor.execute("SELECT club_id FROM public.users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s));", (username_or_club,))
    result = cursor.fetchone()

    if result:
        club_id = result[0]
    else:
        club_id = username_or_club

    print(f"\n✅ شناسه باشگاه تایید شد: '{club_id}'")
    print(f"⏳ در حال افزودن ۳۰ عضو جدید فرضی برای باشگاه '{club_id}'...")

    now = datetime.now(TEHRAN_TZ)
    
    peak_hours = [17, 18, 18, 19, 19, 19, 20, 20, 21]
    regular_hours = [8, 9, 10, 11, 14, 15, 16, 22]
    all_hours = peak_hours + regular_hours

    risk_profiles = ['high_risk'] * 6 + ['medium_risk'] * 6 + ['low_risk'] * 18
    random.shuffle(risk_profiles)

    added_count = 0
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

        # ۱. درج عضو
        cursor.execute("""
            INSERT INTO public.members (first_name, last_name, national_id, phone_number, club_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING member_id;
        """, (f_name, l_name, national_id, phone_number, club_id))
        
        member_id = cursor.fetchone()[0]
        total_sessions = random.choice([12, 24])
        
        # ۲. تنظیم پارامترها متناسب با پروفایل ریسک
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

        # محاسبه تاریخ دقیق فقط به صورت date جهت جلوگیری از خطای تایم‌زون در پستگرس
        start_date = (now - timedelta(days=days_active)).date()
        end_date = start_date + timedelta(days=30)
        sub_status = 'ACTIVE'

        # ۳. درج اشتراک
        cursor.execute("""
            INSERT INTO public.subscriptions (member_id, remaining_sessions, start_date, end_date, status, club_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING subscription_id;
        """, (member_id, remaining, start_date, end_date, sub_status, club_id))

        sub_id = cursor.fetchone()[0]

        # ۴. درج ترددها
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

        added_count += 1

    conn.commit()
    print(f"✅ با موفقیت ۳۰ عضو جدید برای باشگاه '{club_id}' اضافه شد!")
    conn.close()

if __name__ == "__main__":
    username_input = input("لطفاً نام کاربری یا شناسه باشگاه را وارد کنید: ").strip()
    while not username_input:
        username_input = input("شناسه نمی‌تواند خالی باشد: ").strip()
        
    generate_data(username_input)