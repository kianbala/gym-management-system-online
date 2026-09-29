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

def generate_data(club_id="admin"):
    conn = get_connection()
    cursor = conn.cursor()

    print(f"⏳ در حال افزودن ۳۰ عضو جدید برای باشگاه '{club_id}'...")
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

        # درج عضو جدید
        cursor.execute("""
            INSERT INTO public.members (first_name, last_name, national_id, phone_number, club_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING member_id;
        """, (f_name, l_name, national_id, phone_number, club_id))
        
        member_id = cursor.fetchone()[0]

        total_sessions = random.choice([12, 24])
        
        # 🎯 تعیین وضعیت اشتراک: ۸۰٪ ACTIVE و ۲۰٪ EXPIRED
        sub_status = random.choices(['ACTIVE', 'EXPIRED'], weights=[0.80, 0.20])[0]

        if sub_status == 'EXPIRED':
            # کاربر منقضی‌شده: تاریخ شروع قدیمی (۴۵ تا ۶۰ روز پیش)
            start_days_ago = random.randint(45, 60)
            start_date = now - timedelta(days=start_days_ago)
            end_date = start_date + timedelta(days=30)
            
            remaining = random.choice([0, 0, 0, random.randint(1, 2)])
            days_active = start_days_ago
            
            last_checkin_days_ago = random.randint(15, min(35, days_active))
            
        else:
            # کاربر فعال: ثبت‌نام در طی ۲۸ روز گذشته
            days_active = random.randint(1, 28)
            start_date = now - timedelta(days=days_active)
            end_date = start_date + timedelta(days=30)

            # الگوی رفتاری
            pattern = random.choices(['regular', 'at_risk', 'churning'], weights=[0.60, 0.25, 0.15])[0]

            if pattern == 'regular':
                last_checkin_days_ago = random.randint(0, min(3, days_active))
                remaining = random.randint(4, total_sessions - 1)
                
            elif pattern == 'at_risk':
                min_days = min(6, days_active)
                max_days = min(10, days_active)
                last_checkin_days_ago = random.randint(min_days, max_days)
                remaining = random.randint(1, 3)
                
            else: # churning
                min_days = min(12, days_active)
                max_days = min(25, days_active)
                last_checkin_days_ago = random.randint(min_days, max_days)
                remaining = 0

        # درج اشتراک
        cursor.execute("""
            INSERT INTO public.subscriptions (member_id, remaining_sessions, start_date, end_date, status, club_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING subscription_id;
        """, (member_id, remaining, start_date, end_date, sub_status, club_id))

        sub_id = cursor.fetchone()[0]

        # ثبت آخرین تردد
        hour = random.choice(all_hours)
        minute = random.randint(0, 59)
        last_checkin_time = (now - timedelta(days=last_checkin_days_ago)).replace(hour=hour, minute=minute)

        cursor.execute("""
            INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
            VALUES (%s, %s, %s, %s);
        """, (member_id, sub_id, last_checkin_time, club_id))

        # ثبت ترددهای گذشته به تعداد جلسات استفاده‌شده
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
    print(f"✅ با موفقیت {added_count} عضو جدید برای باشگاه '{club_id}' در Supabase اضافه شدند!")
    conn.close()

if __name__ == "__main__":
    # در صورت نیاز می‌توانید اسم باشگاه را اینجا تغییر دهید
    generate_data("admin")