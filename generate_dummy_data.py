import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from db_manager import get_connection, get_or_create_package_id

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# ------------------------------------------------------------------
# تنظیمات داده نمونه
# ------------------------------------------------------------------
TOTAL_MEMBERS = 60
RISK_SHARE = {"high": 0.15, "medium": 0.25}          # بقیه (۶۰٪) ریسک پایین
# بازه امتیاز هر سطح؛ همان آستانه‌های صفحه «آمار و گزارشات» (۷۰ و ۴۰)
SCORE_BAND = {"high": (70.0, 100.0), "medium": (40.0, 69.9), "low": (0.0, 39.9)}

PHONE_PREFIXES = ['0912', '0919', '0935', '0936', '0937', '0910', '0911', '0913', '0914', '0901', '0902', '0990']

FIRST_NAMES = [
    'علی', 'محمد', 'امیر', 'حسین', 'مهدی', 'رضا', 'سروش', 'آرش', 'کامران', 'نوید',
    'سارا', 'نیلوفر', 'مریم', 'زهرا', 'پریسا', 'فاطمه', 'مهرنوش', 'کیانا', 'مینا', 'نرگس'
]

LAST_NAMES = [
    'رضایی', 'محمدی', 'احمدی', 'کریمی', 'حسینی', 'کاظمی', 'قاسمی', 'نوری', 'مرادی', 'ابراهیمی',
    'صادقی', 'حیدری', 'موسوی', 'نجفی', 'مظفری', 'شریفی', 'فراهانی', 'جعفری', 'اکبری', 'باقری'
]


def make_national_id():
    """
    کد ملی ۱۰ رقمی ساختگی با رقم کنترل «درست» (مثل کدهای واقعی؛ صفر ابتدایی هم ممکن است).
    این‌طور هشدار رقم کنترل صفحه «ثبت عضو جدید» برای داده‌های نمونه فعال نمی‌شود.
    """
    while True:
        base = "".join(random.choice("0123456789") for _ in range(9))
        remainder = sum(int(d) * (10 - i) for i, d in enumerate(base)) % 11
        code = base + str(remainder if remainder < 2 else 11 - remainder)
        if len(set(code)) > 1:          # کدهای تک‌رقمی‌تکراری مثل 1111111111 نامعتبرند
            return code


def risk_score(total, remaining, days_absent):
    """
    همان فرمول امتیاز ریسک صفحه «آمار و گزارشات» (اگر آن فرمول را عوض کردید، اینجا هم عوض کنید):
      جلسات از دست‌رفته = روز غیبت × (جلسات بسته ÷ ۳۰)  ← هر کدام ۱۵ امتیاز
      مرحله بسته = ۳۰ × (سهم مصرف‌شده از بسته)²
      جمع با سقف ۱۰۰
    """
    absence_points = days_absent * (total / 30.0) * 15.0
    progress = max(0.0, min(1.0, 1.0 - remaining / total))
    return min(100.0, absence_points + 30.0 * progress ** 2)


def get_user_club_id(cursor, username):
    """بررسی وجود مدیر در پایگاه داده و استخراج شناسه باشگاه او"""
    try:
        cursor.execute(
            "SELECT club_id, id FROM public.users WHERE LOWER(TRIM(username)) = LOWER(TRIM(%s));", 
            (username,)
        )
        res = cursor.fetchone()
        if res:
            # اگر club_id مقدار داشت همان را برمی‌گرداند، در غیر این صورت id کاربر را استفاده می‌کند
            return res[0] if res[0] is not None else res[1]
    except Exception as e:
        print(f"[WARNING] Failed to look up user: {e}")
    
    return None


def build_risk_plan(total_members):
    """فهرست سطح ریسک اعضا (۱۵٪ بالا، ۲۵٪ متوسط، بقیه پایین) به‌صورت درهم"""
    n_high = round(total_members * RISK_SHARE["high"])
    n_medium = round(total_members * RISK_SHARE["medium"])
    plan = ['high'] * n_high + ['medium'] * n_medium + ['low'] * (total_members - n_high - n_medium)
    random.shuffle(plan)
    return plan


def pick_target_score(profile):
    """هدف امتیاز تصادفی داخل بازه سطح؛ برای ریسک پایین کمی به سمت امتیازهای کم متمایل است (واقع‌بینانه‌تر)"""
    lo, hi = SCORE_BAND[profile]
    if profile == 'low':
        return lo + random.betavariate(1.2, 2.2) * (hi - lo)
    return random.uniform(lo, hi)


def pick_checkin_time(now, days_ago, all_hours):
    """زمان آخرین تردد؛ اگر از «الان» جلوتر شد، یک روز عقب می‌رود"""
    hour = random.choice(all_hours)
    minute = random.randint(0, 59)
    t = (now - timedelta(days=days_ago)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t > now:
        t -= timedelta(days=1)
    return t


def sample_member_profile(profile, now, all_hours):
    """
    نمونه‌گیری پارامترهای عضو تا امتیاز واقعی‌اش نزدیک یک هدف تصادفی داخل بازه سطحش بیفتد.
    به‌جای «همه ریسک بالا = ۱۰۰»، امتیازها داخل ۷۰ تا ۱۰۰ (و به همین ترتیب متوسط و پایین) پخش می‌شوند.
    """
    lo, hi = SCORE_BAND[profile]
    target = pick_target_score(profile)

    for attempt in range(30000):
        tolerance = 3.0 if attempt < 10000 else 10.0       # اگر هدف سخت بود، کمی آزادتر
        total = random.choice([12, 24])
        remaining = random.randint(0, total - 1)
        last_time = pick_checkin_time(now, random.randint(0, 22), all_hours)
        days_absent = (now.date() - last_time.date()).days
        days_active = random.randint(max(days_absent, 1), 29)
        used = total - remaining
        if used - 1 > days_active - days_absent:           # ترددهای قبلی باید در روزهای «جدا» و قبل از آخرین تردد جا شوند
            continue                                       # (یعنی حداکثر یک ورود در روز؛ مثلاً نمی‌شود ۲۱ جلسه مصرف کرد و ۱۵ روز غایب بود)

        score = risk_score(total, remaining, days_absent)
        if not (lo <= score <= hi):
            continue
        near = abs(score - target) <= tolerance
        if hi >= 100.0 and target >= 100.0 - tolerance and score >= 100.0 - tolerance:
            near = True                                    # هدف نزدیک سقف: ۱۰۰ هم پذیرفته می‌شود
        if near:
            return {"total": total, "remaining": remaining, "last_time": last_time,
                    "days_absent": days_absent, "days_active": days_active, "score": score}

    raise RuntimeError(f"Could not sample a '{profile}' member profile")


def generate_data(username):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ۱. بررسی وجود مدیر سیستم
        club_id = get_user_club_id(cursor, username)

        if club_id is None:
            print(f"\n[ERROR] User '{username}' was not found in the database.")
            return

        print(f"\n[OK] Admin verified. Club ID: '{club_id}'")
        print(f"[INFO] Creating {TOTAL_MEMBERS} sample members and their check-ins...")

        now = datetime.now(TEHRAN_TZ)
        
        peak_hours = [17, 18, 18, 19, 19, 19, 20, 20, 21]
        regular_hours = [8, 9, 10, 11, 14, 15, 16, 22]
        all_hours = peak_hours + regular_hours

        risk_profiles = build_risk_plan(TOTAL_MEMBERS)

        package_ids = {}                                   # تعداد جلسه ← شناسه بسته (برای هر باشگاه فقط یک‌بار ساخته/پیدا می‌شود)
        used_names = set()
        planned_scores = {'high': [], 'medium': [], 'low': []}
        added_count = 0
        total_checkins_added = 0

        while added_count < TOTAL_MEMBERS:
            risk_profile = risk_profiles[added_count]
            f_name = random.choice(FIRST_NAMES)
            l_name = random.choice(LAST_NAMES)
            if (f_name, l_name) in used_names:             # نام و نام خانوادگی تکراری نباشد
                continue

            national_id = make_national_id()
            phone_number = f"{random.choice(PHONE_PREFIXES)}{random.randint(1000000, 9999999)}"

            cursor.execute(
                "SELECT 1 FROM public.members WHERE (national_id = %s OR phone_number = %s) AND club_id = %s", 
                (national_id, phone_number, club_id)
            )
            if cursor.fetchone():
                continue

            # پارامترهای عضو (بسته، جلسه باقی‌مانده، آخرین تردد، ...) با امتیاز ریسک هدف
            profile = sample_member_profile(risk_profile, now, all_hours)
            total_sessions = profile["total"]
            remaining = profile["remaining"]
            last_checkin_time = profile["last_time"]
            days_active = profile["days_active"]
            last_checkin_days_ago = profile["days_absent"]

            # درج عضو
            cursor.execute("""
                INSERT INTO public.members (first_name, last_name, national_id, phone_number, club_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING member_id;
            """, (f_name, l_name, national_id, phone_number, club_id))
            
            member_id = cursor.fetchone()[0]

            start_date = (now - timedelta(days=days_active)).date()
            end_date = start_date + timedelta(days=30)
            sub_status = 'ACTIVE'

            # درج اشتراک
            if total_sessions not in package_ids:
                package_ids[total_sessions] = get_or_create_package_id(cursor, club_id, total_sessions, 30)

            cursor.execute("""
                INSERT INTO public.subscriptions (member_id, package_id, remaining_sessions, start_date, end_date, status, club_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING subscription_id;
            """, (member_id, package_ids[total_sessions], remaining, start_date, end_date, sub_status, club_id))

            sub_id = cursor.fetchone()[0]

            # درج ترددها (همیشه حداقل یک تردد: آخرین تردد)
            used_sessions = total_sessions - remaining

            cursor.execute("""
                INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
                VALUES (%s, %s, %s, %s);
            """, (member_id, sub_id, last_checkin_time, club_id))
            total_checkins_added += 1

            # ترددهای قبلی: هر کدام در یک روز جدا، بعد از روز آخرین تردد تا روز شروع اشتراک (حداکثر یک ورود در روز)
            past_days = random.sample(range(last_checkin_days_ago + 1, days_active + 1), used_sessions - 1)
            for past_days_ago in past_days:
                past_hour = random.choice(all_hours)
                past_minute = random.randint(0, 59)

                past_checkin_time = (now - timedelta(days=past_days_ago)).replace(
                    hour=past_hour, minute=past_minute, second=0, microsecond=0
                )

                cursor.execute("""
                    INSERT INTO public.checkins (member_id, subscription_id, checkin_time, club_id)
                    VALUES (%s, %s, %s, %s);
                """, (member_id, sub_id, past_checkin_time, club_id))
                total_checkins_added += 1

            used_names.add((f_name, l_name))
            planned_scores[risk_profile].append(profile["score"])
            added_count += 1

        conn.commit()
        print(f"[OK] Created {TOTAL_MEMBERS} members and {total_checkins_added} check-in records for admin '{username}' (club ID: {club_id}).")
        for level in ('high', 'medium', 'low'):
            scores = planned_scores[level]
            if scores:
                print(f"[INFO] Risk {level:<6}: {len(scores):>2} members, score range {min(scores):.1f} - {max(scores):.1f}")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Failed while inserting data: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    username_input = input("Enter the admin username: ").strip()
    while not username_input:
        username_input = input("Username cannot be empty. Enter the admin username: ").strip()
        
    generate_data(username_input)
