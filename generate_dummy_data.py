import random
from datetime import datetime, timedelta
from db_manager import supabase

FIRST_NAMES = [
    'علی', 'محمد', 'امیر', 'حسین', 'مهدی', 'رضا', 'سروش', 'آرش', 'کامران', 'نوید',
    'سارا', 'نیلوفر', 'مریم', 'زهرا', 'پریسا', 'فاطمه', 'مهرنوش', 'کیانا', 'مینا', 'نرگس'
]

LAST_NAMES = [
    'رضایی', 'محمدی', 'احمدی', 'کریمی', 'حسینی', 'کاظمی', 'قاسمی', 'نوری', 'مرادی', 'ابراهیمی',
    'صادقی', 'حیدری', 'موسوی', 'نجفی', 'مظفری', 'شریفی', 'فراهانی', 'جعفری', 'اکبری', 'باقری'
]

def generate_dummy_data_for_club(club_id):
    print(f"⏳ در حال افزودن ۳۰ عضو نمونه و تاریخچه تردد برای باشگاه: {club_id} ...")
    now = datetime.now()
    
    peak_hours = [17, 18, 18, 19, 19, 19, 20, 20, 21]
    regular_hours = [8, 9, 10, 11, 14, 15, 16, 22]
    all_hours = peak_hours + regular_hours

    added_count = 0
    for i in range(1, 31):
        f_name = random.choice(FIRST_NAMES)
        l_name = random.choice(LAST_NAMES)
        full_name = f"{f_name} {l_name}"
        
        unique_seed = int(now.timestamp()) + i + random.randint(100, 999)
        national_id = f"{1000000000 + (unique_seed * 123) % 899999999}"[:10]
        phone_number = f"0912{random.randint(1000000, 9999999)}"

        # 🎯 تعیین وضعیت اعتبار و تاریخ عضویت
        sub_status = random.choices(['active', 'expired'], weights=[0.80, 0.20])[0]

        if sub_status == 'expired':
            days_active = random.randint(45, 60)
            subscription_days = 0
            last_checkin_days_ago = random.randint(15, min(35, days_active))
        else:
            days_active = random.randint(1, 28)
            subscription_days = random.randint(5, 30)
            
            pattern = random.choices(['regular', 'at_risk', 'churning'], weights=[0.60, 0.25, 0.15])[0]
            if pattern == 'regular':
                last_checkin_days_ago = random.randint(0, min(3, days_active))
            elif pattern == 'at_risk':
                last_checkin_days_ago = random.randint(min(6, days_active), min(10, days_active))
            else: # churning
                last_checkin_days_ago = random.randint(min(12, days_active), min(25, days_active))

        join_date = (now - timedelta(days=days_active)).date().isoformat()

        # ۱. ثبت عضو در Supabase
        member_data = {
            "name": full_name,
            "phone": phone_number,
            "national_id": national_id,
            "join_date": join_date,
            "subscription_days": subscription_days,
            "status": sub_status,
            "club_id": club_id
        }
        
        member_res = supabase.table("members").insert(member_data).execute()
        if not member_res.data:
            continue

        member_id = member_res.data[0]['id']

        # ۲. ثبت آخرین تردد
        hour = random.choice(all_hours)
        minute = random.randint(0, 59)
        last_checkin_time = (now - timedelta(days=last_checkin_days_ago)).replace(hour=hour, minute=minute)

        attendance_records = [{
            "member_id": member_id,
            "check_in_time": last_checkin_time.isoformat(),
            "club_id": club_id
        }]

        # ۳. ثبت تردد‌های گذشته به صورت تصادفی
        used_sessions = random.randint(2, 8)
        for _ in range(used_sessions):
            past_days_ago = random.randint(last_checkin_days_ago + 1, days_active)
            past_hour = random.choice(all_hours)
            past_minute = random.randint(0, 59)
            past_checkin_time = (now - timedelta(days=past_days_ago)).replace(hour=past_hour, minute=past_minute)
            
            attendance_records.append({
                "member_id": member_id,
                "check_in_time": past_checkin_time.isoformat(),
                "club_id": club_id
            })

        supabase.table("attendance").insert(attendance_records).execute()
        added_count += 1

    print(f"✅ با موفقیت {added_count} عضو و تاریخچه تردد نمونه برای اکانت '{club_id}' در Supabase ایجاد شدند!")

if __name__ == "__main__":
    # نام اکانتی که می‌خواهید برای آن اعضای نمونه درست شود را بنویسید:
    target_club = input("نام کاربری اکانت/باشگاه مورد نظر را وارد کنید (مثلا kian): ").strip()
    if target_club:
        generate_dummy_data_for_club(target_club)
    else:
        print("❌ نام کاربری وارد نشد.")
