import pandas as pd
import numpy as np
import warnings
from db_manager import get_active_members, get_attendance_logs, get_connection

warnings.filterwarnings('ignore', category=UserWarning)

# تعریف نام استاندارد تایم‌زون به صورت متنی برای پانداس
TEHRAN_TZ_STR = 'Asia/Tehran'

def parse_to_tehran(dt_series):
    """تبدیل دقیق و هوشمند سری زمان‌های Pandas به تایم‌زون تهران"""
    parsed = pd.to_datetime(dt_series, utc=True)
    return parsed.dt.tz_convert(TEHRAN_TZ_STR)

def get_hourly_occupancy(club_id):
    """تحلیل و استخراج میزان شلوغی باشگاه بر اساس ساعات شبانه‌روز"""
    try:
        logs = get_attendance_logs(club_id)
        if not logs:
            return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})
        
        df = pd.DataFrame(logs)
        df['checkin_datetime'] = parse_to_tehran(df['check_in_time'])
        df['hour'] = df['checkin_datetime'].dt.hour
        
        hourly_counts = df.groupby('hour').size().reset_index(name='checkin_count')
        
        all_hours = pd.DataFrame({'hour': list(range(0, 24))})
        result = pd.merge(all_hours, hourly_counts, on='hour', how='left').fillna(0)
        result['checkin_count'] = result['checkin_count'].astype(int)
        
        return result
    except Exception as e:
        print(f"⚠️ خطا در محاسبه ساعات شلوغی: {e}")
        return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})

def get_subscription_checkin_counts(club_id):
    """استخراج تعداد ترددهای انجام‌شده برای اشتراک‌های فعال"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT subscription_id, COUNT(*) 
        FROM public.checkins 
        WHERE club_id = %s AND subscription_id IS NOT NULL 
        GROUP BY subscription_id
    """, (club_id,))
    rows = cursor.fetchall()
    conn.close()
    
    # تبدیل صریح کلیدها به int جهت اطمینان از همخوانی تایپ‌ها
    result = {}
    for r in rows:
        if r[0] is not None:
            try:
                result[int(r[0])] = int(r[1])
            except (ValueError, TypeError):
                result[r[0]] = int(r[1])
    return result

def predict_churn_risk(club_id):
    """تحلیل ریسک ریزش اعضا بر اساس مدل دقیق شدت غیبت و وزن پایان بسته"""
    try:
        raw_members = get_active_members(club_id)
        if not raw_members:
            return pd.DataFrame()
            
        df_members = pd.DataFrame(raw_members)
        
        attendance_logs = get_attendance_logs(club_id)
        last_checkin_map = {}
        if attendance_logs:
            df_att = pd.DataFrame(attendance_logs)
            df_att['check_in_time'] = parse_to_tehran(df_att['check_in_time'])
            last_att = df_att.groupby('member_id')['check_in_time'].max().to_dict()
            last_checkin_map = last_att

        sub_checkins = get_subscription_checkin_counts(club_id)
        
        # استفاده از Timestamp همگام با پانداس برای جلوگیری از خطای تفریق
        now_tehran = pd.Timestamp.now(tz=TEHRAN_TZ_STR)
        
        # ۱. محاسبه روزهای غیبت با تایم‌زون دقیق
        def calc_days_absent(row):
            m_id = row['id']
            if m_id in last_checkin_map:
                last_t = last_checkin_map[m_id]
                diff = (now_tehran - last_t).days
                return max(0, diff)
            return 15  # پیش‌فرض برای افرادی که هنوز هیچ ترودی ثبت نکرده‌اند

        df_members['days_since_last_checkin'] = df_members.apply(calc_days_absent, axis=1)
        
        # ۲. محاسبه نمره ریسک
        def calculate_risk_score(row):
            days = row['days_since_last_checkin']
            remaining = row.get('subscription_days', 0) or 0
            sub_id = row.get('subscription_id')
            
            try:
                sub_id_key = int(sub_id) if sub_id is not None else None
            except (ValueError, TypeError):
                sub_id_key = sub_id
                
            used_sessions = sub_checkins.get(sub_id_key, 0)
            calculated_total = remaining + used_sessions
            
            # تشخیص قطعی نوع بسته (۱۲ یا ۲۴)
            total_sessions = 24 if calculated_total > 12 else 12
            
            # الف) محاسبه شدت غیبت
            expected_rate = total_sessions / 30.0
            s_absence = days * expected_rate * 15.0
            
            # ب) محاسبه وزن پایان بسته (تابع درجه دو)
            progress = 1.0 - (float(remaining) / float(total_sessions))
            progress = max(0.0, min(1.0, progress))
            s_lifecycle = 30.0 * (progress ** 2)
            
            # مجموع امتیاز (محدود به سقف ۱۰۰)
            total_score = min(100.0, s_absence + s_lifecycle)
            return round(float(total_score), 1)

        df_members['churn_risk_score'] = df_members.apply(calculate_risk_score, axis=1)
        
        # ۳. نگاشت بازه‌های ریسک به برچسب‌ها
        def map_to_label(score):
            if score >= 70:
                return '🔴 بالا (High)'
            elif score >= 40:
                return '🟡 متوسط (Medium)'
            else:
                return '🟢 پایین (Low)'
                
        df_members['risk_level'] = df_members['churn_risk_score'].apply(map_to_label)
        
        return df_members

    except Exception as e:
        print(f"⚠️ خطا در محاسبه پیش‌بینی ریزش: {e}")
        return pd.DataFrame()