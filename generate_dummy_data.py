import random
from datetime import datetime, timedelta
from db_manager import supabase

FIRST_NAMES = [
    'Ali', 'Mohammad', 'Amir', 'Hossein', 'Mehdi', 'Reza', 'Soroush', 'Arash', 'Kamran', 'Navid',
    'Sara', 'Niloofar', 'Maryam', 'Zahra', 'Parisa', 'Fatemeh', 'Mehrnoosh', 'Kiana', 'Mina', 'Narges'
]

LAST_NAMES = [
    'Rezayi', 'Mohammadi', 'Ahmadi', 'Karimi', 'Hosseini', 'Kazemi', 'Ghasemi', 'Nouri', 'Moradi', 'Ebrahimi',
    'Sadeghi', 'Heidari', 'Mousavi', 'Najafi', 'Mozaffari', 'Sharifi', 'Farahani', 'Jafari', 'Akbari', 'Bagheri'
]

def generate_dummy_data_for_manager(username):
    # ۱. دریافت اطلاعات مدیر از جدول users
    user_res = supabase.table("users").select("*").eq("username", username).execute()
    if not user_res.data:
        print(f"❌ خطا: مدیری با نام کاربری '{username}' در دیتابیس یافت نشد!")
        return

    user_data = user_res.data[0]
    club_id = user_data.get("club_id", username)

    print(f"⏳ در حال ساخت ۳۰ عضو نمونه و تاریخچه تردد برای باشگاه '{club_id}' (مدیر: '{username}')...")
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

        sub_status = random.choices(['active', 'expired'], weights=[0.80, 0.20])[0]

        if sub_status == 'expired':
            days_active = random.randint(45, 60)
            subscription_days = 0
            sessions_left = 0  # جلسات منقضی‌شده
            last_checkin_days_ago = random.randint(15, min(35, days_active))
        else:
            days_active = random.randint(1, 28)
            subscription_days = random.randint(5, 30)
            
            pattern = random.choices(['regular', 'at_risk', 'churning'], weights=[0.60, 0.25, 0.15])[0]
            if pattern == 'regular':
                sessions_left = random.randint(6, 16)  # اعضای فعال جلسات بیشتری دارند
                last_checkin_days_ago = random.randint(0, min(3, days_active))
            elif pattern == 'at_risk':
                sessions_left = random.randint(1, 4)   # جلسات رو به اتمام
                last_checkin_days_ago = random.randint(min(6, days_active), min(10, days_active))
            else: # churning
                sessions_left = random.randint(0, 2)   # بدون جلسه یا در معرض ریزش
                last_checkin_days_ago = random.randint(min(12, days_active), min(25, days_active))

        join_date = (now - timedelta(days=days_active)).date().isoformat()

        # ۲. ثبت عضو جدید همراه با تعداد جلسات باقی‌مانده (sessions_left)
        member_data = {
            "name": full_name,
            "phone": phone_number,
            "national_id": national_id,
            "join_date": join_date,
            "subscription_days": subscription_days,
            "sessions_left": sessions_left,  # 👈 افزودن جلسات نمونه
            "status": sub_status,
            "club_id": club_id
        }
        
        member_res = supabase.table("members").insert(member_data).execute()
        if not member_res.data:
            continue

        member_id = member_res.data[0]['id']

        # ۳. ثبت آخرین تردد
        hour = random.choice(all_hours)
        minute = random.randint(0, 59)
        last_checkin_time = (now - timedelta(days=last_checkin_days_ago)).replace(hour=hour, minute=minute)

        attendance_records = [{
            "member_id": member_id,
            "check_in_time": last_checkin_time.isoformat(),
            "club_id": club_id
        }]

        # ۴. ثبت سوابق تردد گذشته
        used_sessions = random.randint(2, 8)
        for _ in range(used_sessions):
            min_past = last_checkin_days_ago + 1
            max_past = max(min_past, days_active)
            
            past_days_ago = random.randint(min_past, max_past)
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

    print(f"✅ تعداد {added_count} عضو نمونه با موفقیت همراه با جلسات و تاریخچه تردد برای مدیر '{username}' ثبت شدند!")

if __name__ == "__main__":
    target_username = input("نام کاربری مدیر آنلاین را وارد کنید (مثلاً admin): ").strip()
    if target_username:
        generate_dummy_data_for_manager(target_username)
    else:
        print("❌ نام کاربری وارد نشد.")