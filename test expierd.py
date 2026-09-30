import random
from datetime import datetime, timedelta
from db_manager import get_connection, add_member

def get_available_clubs():
    """دریافت لیست تمام باشگاه‌های ثبت‌شده در سیستم"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT club_id FROM users;")
        clubs = cursor.fetchall()
        club_list = []
        for c in clubs:
            c_id = c['club_id'] if isinstance(c, dict) else c[0]
            if c_id:
                club_list.append(c_id)
        return club_list
    except Exception as e:
        print(f"خطا در دریافت لیست باشگاه‌ها: {e}")
        return []
    finally:
        conn.close()

def insert_expired_test_user():
    # ۱. دریافت لیست باشگاه‌ها و گرفتن ورودی از کاربر
    clubs = get_available_clubs()
    
    if not clubs:
        print("❌ هیچ باشگاه یا اکانتی در سیستم یافت نشد!")
        return

    print("\n🏢 لیست باشگاه‌های موجود در سیستم:")
    for idx, c_id in enumerate(clubs, 1):
        print(f"  {idx}. {c_id}")
    
    selected_club_id = None
    user_input = input("\nلطفاً شناسه باشگاه (club_id) یا شماره آن را وارد کنید: ").strip()

    if user_input.isdigit() and 1 <= int(user_input) <= len(clubs):
        selected_club_id = clubs[int(user_input) - 1]
    elif user_input in clubs:
        selected_club_id = user_input
    else:
        selected_club_id = user_input

    print(f"\n🎯 باشگاه انتخاب‌شده: '{selected_club_id}'")

    # ۲. ساخت شماره همراه و کد ملی تصادفی
    rand_suffix = str(random.randint(1000, 9999))
    name = f"رضا منقضی شده ({rand_suffix})"
    phone = f"0999{rand_suffix}123"
    national_id = f"99{rand_suffix}1234"
    
    # ۳. ثبت عضو جدید در باشگاه انتخابی
    success, msg = add_member(name, phone, national_id, selected_club_id, subscription_days=0)
    print(f"\nنتیجه ثبت عضو: {msg}")
    
    if not success:
        print("❌ ثبت عضو اولیه ناموفق بود.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # ۴. دریافت member_id کاربر تازه ایجادشده
        cursor.execute("SELECT member_id FROM members WHERE national_id = %s AND club_id = %s;", (national_id, selected_club_id))
        member = cursor.fetchone()
        
        if not member:
            print("❌ کاربر پس از ثبت یافت نشد.")
            return

        member_id = member['member_id'] if isinstance(member, dict) else member[0]
        
        # ۵. درج یک اشتراک منقضی‌شده (تنظیم ستون صحیح remaining_sessions به جای subscription_days)
        past_start_date = (datetime.now() - timedelta(days=40)).date()
        past_end_date = (datetime.now() - timedelta(days=10)).date()
        
        cursor.execute("""
            INSERT INTO subscriptions (member_id, club_id, remaining_sessions, start_date, end_date, status)
            VALUES (%s, %s, %s, %s, %s, 'EXPIRED');
        """, (member_id, selected_club_id, 0, past_start_date, past_end_date))
        
        conn.commit()
        
        print("\n✅ داده تست با موفقیت ایجاد گردید!")
        print(f"👤 نام عضو: {name}")
        print(f"🆔 کد عضویت: {member_id}")
        print(f"🏢 باشگاه: {selected_club_id}")
        print(f"📅 تاریخ انقضا: {past_end_date} (۱۰ روز پیش)")
        print(f"🔴 وضعیت: EXPIRED")

    except Exception as e:
        conn.rollback()
        print(f"❌ خطا در ثبت اشتراک منقضی‌شده: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    insert_expired_test_user()