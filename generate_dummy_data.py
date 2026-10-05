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

def generate_data(username):
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Check user existence & retrieve club_id
    cursor.execute("SELECT club_id FROM public.users WHERE username = %s;", (username,))
    result = cursor.fetchone()

    if not result:
        print(f"\n❌ Error: Username '{username}' not found in the system! Please ensure this user exists.")
        conn.close()
        return

    club_id = result[0]
    print(f"\n✅ Username '{username}' verified. (Club ID: '{club_id}')")
    print(f"⏳ Adding 30 new active members for club '{club_id}'...")

    # Exact Tehran time with timezone
    now = datetime.now(TEHRAN_TZ)
    
    peak_hours = [17, 18, 18, 19, 19, 19, 20, 20, 21]
    regular_hours = [8, 9, 10, 11, 14, 15, 16, 22]
    all_hours = peak_hours + regular_hours

    # Exact Distribution: 6 High Risk (20%), 6 Medium Risk (20%), 18 Low Risk (60%)
    risk_profiles = ['high_risk'] * 6 + ['medium_risk'] * 6 + ['low_risk'] * 18
    random.shuffle(risk_profiles)

    added_count = 0
    # Guaranteed loop until exactly 30 members are inserted
    while added_count < 30:
        risk_profile = risk_profiles[added_count]
        f_name = random.choice(FIRST_NAMES)
        l_name = random.choice(LAST_NAMES)
        
        unique_seed = int(now.timestamp()) + added_count + random.randint(100, 99999)
        national_id = f"{1000000000 + (unique_seed * 123) % 899999999}"[:10]
        phone_number = f"0912{random.randint(1000000, 9999999)}"

        cursor.execute(
            "SELECT 1 FROM public.members WHERE (national_id = %s OR phone_number = %s) AND club_id = %s", 
            (national_id, phone_number, club_id)
        )
        if cursor.fetchone():
            continue

        # 1. Insert Member
        cursor.execute("""
            INSERT INTO public.members (first_name, last_name, national_id, phone_number, club_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING member_id;
        """, (f_name, l_name, national_id, phone_number, club_id))
        
        member_id = cursor.fetchone()[0]

        # Select package type: 12 or 24 sessions
        total_sessions = random.choice([12, 24])
        
        # 2. Assign parameters tuned EXACTLY for ai_analytics risk ranges
        if risk_profile == 'high_risk':
            # Target Score >= 70
            last_checkin_days_ago = random.randint(9, 20)
            # Days active bounded to max 29 days so end_date remains strictly in the future
            days_active = random.randint(last_checkin_days_ago + 1, 29)
            remaining = random.randint(0, 3)

        elif risk_profile == 'medium_risk':
            # Target Score: 40 <= Score < 70
            if total_sessions == 12:
                remaining = random.randint(2, 5)
                last_checkin_days_ago = random.randint(5, 7)
            else:  # 24 sessions
                remaining = random.randint(13, 15)
                last_checkin_days_ago = random.randint(3, 4)
            days_active = random.randint(last_checkin_days_ago + 1, 29)

        else:  # low_risk
            # Target Score: Score < 40
            if total_sessions == 12:
                remaining = random.randint(6, 11)
                last_checkin_days_ago = random.randint(0, 3)
            else:  # 24 sessions
                remaining = random.randint(16, 23)
                last_checkin_days_ago = random.randint(0, 2)
            days_active = random.randint(last_checkin_days_ago + 1, 29)

        start_date = now - timedelta(days=days_active)
        end_date = start_date + timedelta(days=30)
        sub_status = 'ACTIVE'

        # 3. Insert Subscription
        cursor.execute("""
            INSERT INTO public.subscriptions (member_id, remaining_sessions, start_date, end_date, status, club_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING subscription_id;
        """, (member_id, remaining, start_date, end_date, sub_status, club_id))

        sub_id = cursor.fetchone()[0]

        # 4. Calculate Exact Used Sessions & Record Attendance
        used_sessions = total_sessions - remaining

        if used_sessions > 0:
            # Record last check-in with Iran timezone
            hour = random.choice(all_hours)
            minute = random.randint(0, 59)
            
            last_checkin_time = (now - timedelta(days=last_checkin_days_ago)).replace(
                hour=hour, minute=minute, second=0, microsecond=0, tzinfo=TEHRAN_TZ
            )

            cursor.execute("""
                INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
                VALUES (%s, %s, %s, %s);
            """, (member_id, sub_id, last_checkin_time, club_id))

            # Record past check-ins
            past_sessions_count = used_sessions - 1
            start_past_days = min(last_checkin_days_ago + 1, days_active)
            end_past_days = days_active

            for _ in range(past_sessions_count):
                past_days_ago = random.randint(start_past_days, end_past_days)
                past_hour = random.choice(all_hours)
                past_minute = random.randint(0, 59)
                
                past_checkin_time = (now - timedelta(days=past_days_ago)).replace(
                    hour=past_hour, minute=past_minute, second=0, microsecond=0, tzinfo=TEHRAN_TZ
                )
                
                cursor.execute("""
                    INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
                    VALUES (%s, %s, %s, %s);
                """, (member_id, sub_id, past_checkin_time, club_id))

        added_count += 1

    conn.commit()
    print(f"✅ Successfully added {added_count} new active members for user '{username}'!")
    print(f"📊 Risk Distribution: 6 High (20%), 6 Medium (20%), 18 Low Risk (60%)")
    conn.close()

if __name__ == "__main__":
    username_input = input("Please enter username: ").strip()
    
    while not username_input:
        username_input = input("Username cannot be empty. Please enter username: ").strip()
        
    generate_data(username_input)