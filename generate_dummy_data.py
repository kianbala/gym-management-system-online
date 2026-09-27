import random
from datetime import datetime, timedelta
from db_manager import supabase

# اسامی و فامیلی‌های فارسی
FIRST_NAMES = [
    'علی', 'محمد', 'امیر', 'حسین', 'مهدی', 'رضا', 'سروش', 'آرش', 'کامران', 'نوید',
    'سارا', 'نیلوفر', 'مریم', 'زهرا', 'پریسا', 'فاطمه', 'مهرنوش', 'کیانا', 'مینا', 'نرگس',
    'پرهام', 'سامان', 'دانیال', 'فرزاد', 'یلدا', 'مونا', 'الهام', 'سپیده'
]

LAST_NAMES = [
    'رضایی', 'محمدی', 'احمدی', 'کریمی', 'حسینی', 'کاظمی', 'قاسمی', 'نوری', 'مرادی', 'ابراهیمی',
    'صادقی', 'حیدری', 'موسوی', 'نجفی', 'مظفری', 'شریفی', 'فراهانی', 'جعفری', 'اکبری', 'باقری'
]

def generate_unique_national_id(existing_ids):
    """تولید کد ملی ۱۰ رقمی کاملاً یکتا"""
    while True:
        nid = "".join([str(random.randint(0, 9)) for _ in range(10)])
        if nid not in existing_ids and not nid.startswith("000"):
            existing_ids.add(nid)
            return nid

def generate_dummy_data_for_manager(username):
    user_res = supabase.table("users").select("*").eq("username", username).execute()
    if not user_res.data:
        print(f"❌ Error: Manager with username '{username}' was not found in database!")
        return

    user_data = user_res.data[0]
    club_id = user_data.get("club_id", username)

    # دریافت کدهای ملی موجود در دیتابیس برای این باشگاه جهت جلوگیری از خطای Duplicate
    existing_members = supabase.table("members").select("national_id").eq("club_id", club_id).execute()
    existing_ids = {m.get("national_id") for m in (existing_members.data or []) if m.get("national_id")}

    print(f"⏳ Generating 30 sample members and attendance history for manager: '{username}' (Club: '{club_id}') ...")
    now = datetime.now()
    
    # ساعات شلوغی و معمولی جهت توزیع واقع‌گرایانه نمودار ساعات شلوغی
    peak_hours = [17, 18, 18, 19, 19, 19, 20, 20, 21]
    regular_hours = [8, 9, 10, 11, 14, 15, 16, 22]
    all_hours = peak_hours + regular_hours

    added_count = 0
    for i in range(1, 31):
        f_name = random.choice(FIRST_NAMES)
        l_name = random.choice(LAST_NAMES)
        full_name = f"{f_name} {l_name}"
        
        national_id = generate_unique_national_id(existing_ids)
        phone_number = f"0912{random.randint(1000000, 9999999)}"

        # تعیین پروفایل رفتار کاربر (از جمله اعضای تازه ثبت‌نام‌شده بدون بسته)
        profile_type = random.choices(
            ['regular', 'at_risk', 'churning', 'expired', 'no_package'], 
            weights=[0.40, 0.20, 0.15, 0.15, 0.10]
        )[0]

        initial_sessions = random.choices([12, 24], weights=[0.60, 0.40])[0]

        if profile_type == 'no_package':   # ثبت اولیه بدون بسته
            sub_status = 'inactive'
            days_active = random.randint(0, 10)
            num_attendances = 0
            last_checkin_days_ago = None
            remaining_sessions = 0
        elif profile_type == 'expired':     # اشتراک منقضی شده
            sub_status = 'expired'
            days_active = random.randint(32, 60)
            num_attendances = min(initial_sessions, random.randint(8, initial_sessions))
            last_checkin_days_ago = random.randint(20, days_active)
            remaining_sessions = 0
        elif profile_type == 'churning':  # ریسک بالا (غیبت طولانی)
            sub_status = 'active'
            days_active = random.randint(15, 28)
            num_attendances = random.randint(1, 3)
            last_checkin_days_ago = random.randint(14, days_active)
            remaining_sessions = max(1, initial_sessions - num_attendances)
        elif profile_type == 'at_risk':   # ریسک متوسط
            sub_status = 'active'
            days_active = random.randint(10, 25)
            num_attendances = random.randint(2, 6)
            last_checkin_days_ago = random.randint(6, 12)
            remaining_sessions = max(1, initial_sessions - num_attendances)
        else:                             # منظم / ریسک پایین
            sub_status = 'active'
            days_active = random.randint(1, 28)
            max_possible_logs = min(initial_sessions - 1, int(days_active * 0.7) + 1)
            num_attendances = random.randint(1, max(1, max_possible_logs))
            last_checkin_days_ago = random.randint(0, min(3, days_active))
            remaining_sessions = max(1, initial_sessions - num_attendances)

        join_date = (now - timedelta(days=days_active)).date().isoformat()

        member_data = {
            "name": full_name,
            "phone": phone_number,
            "national_id": national_id,
            "join_date": join_date,
            "subscription_days": remaining_sessions,
            "status": sub_status,
            "club_id": club_id
        }
        
        try:
            member_res = supabase.table("members").insert(member_data).execute()
            if not member_res.data:
                continue

            member_id = member_res.data[0]['id']

            # ثبت سوابق تردد برای اعضای دارای تردد
            attendance_records = []
            if num_attendances > 0 and last_checkin_days_ago is not None:
                # ۱. ثبت آخرین ورود
                hour = random.choice(all_hours)
                minute = random.randint(0, 59)
                last_checkin_time = (now - timedelta(days=last_checkin_days_ago)).replace(hour=hour, minute=minute)
                attendance_records.append({
                    "member_id": member_id,
                    "check_in_time": last_checkin_time.isoformat(),
                    "club_id": club_id
                })

                # ۲. ثبت ترددهای قبلی
                for _ in range(num_attendances - 1):
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

            if attendance_records:
                supabase.table("attendance").insert(attendance_records).execute()
                
            added_count += 1
        except Exception as e:
            err_msg = str(e).lower()
            if any(term in err_msg for term in ["duplicate", "unique", "23505"]):
                print(f"⚠️ کد ملی تکراری نادیده گرفته شد: {national_id}")
            else:
                print(f"⚠️ خطا در ثبت عضو {full_name}: {e}")

    print(f"✅ Created {added_count} sample members & attendance logs for manager '{username}' (Club: '{club_id}')!")

if __name__ == "__main__":
    target_username = input("Enter manager username (e.g. admin): ").strip()
    if target_username:
        generate_dummy_data_for_manager(target_username)