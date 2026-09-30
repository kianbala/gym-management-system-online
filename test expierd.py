from datetime import datetime, timedelta
from db_manager import get_connection, add_member

def insert_expired_test_user(club_id="club_1"):
    # ۱. ثبت ابتدا به عنوان عضو جدید
    name = "رضا منقضی شده"
    phone = "09999999999"
    national_id = "9999999999"
    
    success, msg = add_member(name, phone, national_id, club_id, subscription_days=0)
    print(msg)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # ۲. پیدا کردن member_id کاربر تازه ساخته شده (استفاده از member_id به جای id)
    cursor.execute("SELECT member_id FROM members WHERE national_id = %s AND club_id = %s;", (national_id, club_id))
    member = cursor.fetchone()
    
    if not member:
        print("❌ کاربر یافت نشد.")
        conn.close()
        return

    # پشتیبانی هم از RealDictCursor (دیکشنری) و هم از Tuple معمولی
    member_id = member['member_id'] if isinstance(member, dict) else member[0]
    
    # ۳. درج دستی یک اشتراک که تاریخ انقضایش ۱۰ روز پیش بوده است
    past_start_date = (datetime.now() - timedelta(days=40)).date()
    past_end_date = (datetime.now() - timedelta(days=10)).date()  # ۱۰ روز پیش انقضا شده
    
    cursor.execute("""
        INSERT INTO subscriptions (member_id, club_id, package_name, remaining_sessions, start_date, end_date, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'EXPIRED');
    """, (member_id, club_id, 'بسته ۱ | ۱۲ جلسه', 0, past_start_date, past_end_date))
    
    conn.commit()
    conn.close()
    print(f"✅ کاربر تست با موفقیت ایجاد شد! (کد عضویت: {member_id})")
    print(f"📅 تاریخ انقضای ثبت‌شده: {past_end_date}")

if __name__ == "__main__":
    # در صورت نیاز کد باشگاه خود را چک کنید (مثلا club_1 یا هر آی‌دی که با آن وارد app می‌شوید)
    insert_expired_test_user("club_1")