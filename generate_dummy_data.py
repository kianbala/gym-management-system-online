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

    # لیست دقیقا ۳۰ عضوی برای تضمین نسبت ۲۰٪ بالا، ۲۰٪ متوسط و ۶۰٪ پایین
    risk_profiles = ['high_risk'] * 6 + ['medium_risk'] * 6 + ['low_risk'] * 18
    random.shuffle(risk_profiles)

    added_count = 0
    for i, risk_profile in enumerate(risk_profiles, 1):
        f_name = random.choice(FIRST_NAMES)
        l_name = random.choice(LAST_NAMES)
        
        unique_seed = int(now.timestamp()) + i + random.randint(100, 999)
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
        
        # ۲. تعیین دقیق الگوی رفتار براساس فرمول هوش مصنوعی جهت دستیابی به بازه ریسک مورد نظر
        if risk_profile == 'high_risk':
            # ریسک بالا (امتیاز >= ۷۰): غیبت ۱۴ تا ۲۵ روز پیش (امتیاز روزها = ۷۰)
            last_checkin_days_ago = random.randint(14, 25)
            days_active = random.randint(last_checkin_days_ago + 1, 28) # تاریخ شروع کمتر از ۳۰ روز پیش جهت فعال ماندن
            remaining = random.choice([0, 1, 2])

        elif risk_profile == 'medium_risk':
            # ریسک متوسط (۴۰ <= امتیاز < ۷۰): غیبت ۶ تا ۹ روز پیش (امتیاز ۳۰-۴۵) + جلسات کم (امتیاز ۱۵) -> کل: ۴۵ تا ۶۰
            last_checkin_days_ago = random.randint(6, 9)
            days_active = random.randint(last_checkin_days_ago + 1, 28)
            remaining = random.randint(1, 3)

        else:
            # ریسک پایین (امتیاز < ۴۰): غیبت ۰ تا ۳ روز پیش (امتیاز ۰-۱۵) + جلسات کافی (امتیاز ۰) -> کل: ۰ تا ۱۵
            last_checkin_days_ago = random.randint(0, 3)
            days_active = random.randint(last_checkin_days_ago + 1, 28)
            remaining = random.randint(4, 12)

        # محاسبه start_date و end_date که حتماً در آینده باشد (اشتراک ACTIVE)
        start_date = now - timedelta(days=days_active)
        end_date = start_date + timedelta(days=30)
        sub_status = 'ACTIVE'

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
    print(f"✅ با موفقیت {added_count} عضو جدید با اشتراک فعال اضافه شدند!")
    print(f"📊 تفکیک دقیق ریسک‌ها: ۶ عضو بالا (۲۰٪)، ۶ عضو متوسط (۲۰٪)، ۱۸ عضو پایین (۶۰٪)")
    conn.close()

if __name__ == "__main__":
    user_input = input("لطفاً نام کاربری (username / club_id) اکانت موردنظر را وارد کنید: ").strip()
    
    while not user_input:
        user_input = input("نام کاربری نمی‌تواند خالی باشد. لطفاً نام کاربری را وارد کنید: ").strip()
        
    generate_data(user_input)