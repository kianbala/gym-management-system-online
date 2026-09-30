import random
from datetime import datetime, timedelta
from db_manager import get_connection

FIRST_NAMES = [
    'علی', 'محمد', 'امیر', 'حسین', 'مهدی', 'رضا', 'سروش', 'آرش', 'کامران', 'نوید',
    'سارا', 'نیلوفر', 'مریم', 'زهرا', 'پریسا', 'فاطمه', 'مهرنوش', 'کیانا', 'مینا', 'نرگس'
]

LAST_NAMES = [
    'رضایی', 'محمدی', 'احمدی', 'کریمی', 'حسینی', 'کاظمی', 'قاسمی', 'نوری', 'مرادی', 'ابراهیمی',
    'صادقی', 'حیدری', 'موسوی', 'نجفی', 'مظفری', 'شریفی', 'فراهانی', 'جعفری', 'اکبری', 'باقری'
]

def generate_data(club_id):
    conn = get_connection()
    cursor = conn.cursor()

    print(f"\n⏳ در حال افزودن ۳۰ عضو جدید با اشتراک فعال برای باشگاه '{club_id}'...")
    now = datetime.now()
    
    peak_hours = [17, 18, 18, 19, 19, 19, 20, 20, 21]
    regular_hours = [8, 9, 10, 11, 14, 15, 16, 22]
    all_hours = peak_hours + regular_hours

    added_count = 0
    for i in range(1, 31):
        f_name = random.choice(FIRST_NAMES)
        l_name = random.choice(LAST_NAMES)
        
        unique_seed = int(now.timestamp()) + i
        national_id = f"{1000000000 + (unique_seed * 123) % 899999999}"[:10]
        phone_number = f"0912{random.randint(1000000, 9999999)}"

        # بررسی تکراری نبودن عضو در این باشگاه
        cursor.execute(
            "SELECT 1 FROM public.members WHERE (national_id = %s OR phone_number = %s) AND club_id = %s", 
            (national_id, phone_number, club_id)
        )
        if cursor.fetchone():
            continue

        # ۱. درج عضو جدید
        cursor.execute("""
            INSERT INTO public.members (first_name, last_name, national_id, phone_number, club_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING member_id;
        """, (f_name, l_name, national_id, phone_number, club_id))
        
        member_id = cursor.fetchone()[0]

        total_sessions = random.choice([12, 24])
        
        # وضعیت همگی ACTIVE است
        sub_status = 'ACTIVE'

        # ۲. تعیین الگوی رفتار براساس ریسک (۲۰٪ ریسک بالا، ۲۰٪ ریسک متوسط، ۶۰٪ ریسک پایین)
        risk_profile = random.choices(
            ['high_risk', 'medium_risk', 'low_risk'], 
            weights=[0.20, 0.20, 0.60]
        )[0]

        if risk_profile == 'high_risk':
            # ریسک بالا (عدم مراجعه طولانی ۱۲ تا ۲۵ روز پیش یا اتمام جلسات)
            days_active = random.randint(14, 28)
            start_date = now - timedelta(days=days_active)
            end_date = start_date + timedelta(days=30)
            
            min_days = min(12, days_active)
            max_days = min(25, days_active)
            last_checkin_days_ago = random.randint(min_days, max_days)
            remaining = random.choice([0, 1])

        elif risk_profile == 'medium_risk':
            # ریسک متوسط (مراجعه ۶ تا ۱۰ روز پیش و ۱ تا ۳ جلسه باقی‌مانده)
            days_active = random.randint(7, 28)
            start_date = now - timedelta(days=days_active)
            end_date = start_date + timedelta(days=30)

            min_days = min(6, days_active)
            max_days = min(10, days_active)
            last_checkin_days_ago = random.randint(min_days, max_days)
            remaining = random.randint(1, 3)

        else:
            # ریسک پایین (مراجعه منظم ۰ تا ۳ روز پیش و جلسات کافی)
            days_active = random.randint(1, 28)
            start_date = now - timedelta(days=days_active)
            end_date = start_date + timedelta(days=30)

            last_checkin_days_ago = random.randint(0, min(3, days_active))
            remaining = random.randint(4, total_sessions - 1)

        # ۳. درج اشتراک فعال
        cursor.execute("""
            INSERT INTO public.subscriptions (member_id, remaining_sessions, start_date, end_date, status, club_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING subscription_id;
        """, (member_id, remaining, start_date, end_date, sub_status, club_id))

        sub_id = cursor.fetchone()[0]

        # ۴. ثبت آخرین تردد
        hour = random.choice(all_hours)
        minute = random.randint(0, 59)
        last_checkin_time = (now - timedelta(days=last_checkin_days_ago)).replace(hour=hour, minute=minute)

        cursor.execute("""
            INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
            VALUES (%s, %s, %s, %s);
        """, (member_id, sub_id, last_checkin_time, club_id))

        # ۵. ثبت ترددهای گذشته متناسب با جلسات استفاده‌شده
        used_sessions = max(0, total_sessions - remaining - 1)
        
        start_past_days = min(last_checkin_days_ago + 1, days_active)
        end_past_days = days_active
        
        for _ in range(used_sessions):
            past_days_ago = random.randint(start_past_days, end_past_days)
            past_hour = random.choice(all_hours)
            past_minute = random.randint(0, 59)
            past_checkin_time = (now - timedelta(days=past_days_ago)).replace(hour=past_hour, minute=past_minute)
            
            cursor.execute("""
                INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
                VALUES (%s, %s, %s, %s);
            """, (member_id, sub_id, past_checkin_time, club_id))
            
        added_count += 1

    conn.commit()
    print(f"✅ با موفقیت {added_count} عضو جدید فعال (۲۰٪ ریسک بالا، ۲۰٪ متوسط، ۶۰٪ پایین) برای باشگاه '{club_id}' اضافه شدند!")
    conn.close()

if __name__ == "__main__":
    user_input = input("لطفاً نام کاربری (username / club_id) اکانت موردنظر را وارد کنید: ").strip()
    
    while not user_input:
        user_input = input("نام کاربری نمی‌تواند خالی باشد. لطفاً نام کاربری را وارد کنید: ").strip()
        
    generate_data(user_input)