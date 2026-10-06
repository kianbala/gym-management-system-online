import pandas as pd
import numpy as np
import warnings
from db_manager import get_active_members, get_attendance_logs, get_connection

warnings.filterwarnings('ignore', category=UserWarning)

TEHRAN_TZ_STR = 'Asia/Tehran'

def clean_id(val):
    """یکسان‌سازی کلیدها جهت جلوگیری از عدم تطابق int, float و str"""
    if pd.isna(val) or val is None or val == '':
        return None
    try:
        return str(int(float(val)))
    except (ValueError, TypeError):
        return str(val).strip()

def parse_to_tehran(dt_series):
    """تبدیل ایمن انواع فرمت‌های زمان به تایم‌زون تهران"""
    parsed = pd.to_datetime(dt_series, utc=True, errors='coerce')
    return parsed.dt.tz_convert(TEHRAN_TZ_STR)

def get_hourly_occupancy(club_id):
    """تحلیل و استخراج میزان شلوغی باشگاه بر اساس ساعات شبانه‌روز"""
    try:
        logs = get_attendance_logs(club_id)
        if not logs:
            return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})
        
        df = pd.DataFrame(logs)
        if 'check_in_time' not in df.columns or df.empty:
            return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})

        df['checkin_datetime'] = parse_to_tehran(df['check_in_time'])
        df = df.dropna(subset=['checkin_datetime'])
        
        if df.empty:
            return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})

        df['hour'] = df['checkin_datetime'].dt.hour.astype(int)
        hourly_counts = df.groupby('hour').size().reset_index(name='checkin_count')
        
        all_hours = pd.DataFrame({'hour': list(range(0, 24))})
        result = pd.merge(all_hours, hourly_counts, on='hour', how='left').fillna(0)
        result['checkin_count'] = result['checkin_count'].astype(int)
        
        return result
    except Exception as e:
        print(f"⚠️ خطا در محاسبه ساعات شلوغی: {e}")
        return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})

def get_subscription_checkin_counts(club_id):
    """استخراج تعداد ترددهای ثبت‌شده برای هر اشتراک"""
    try:
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
        
        result = {}
        for r in rows:
            if r[0] is not None:
                key = clean_id(r[0])
                if key:
                    result[key] = int(r[1])
        return result
    except Exception as e:
        print(f"⚠️ خطا در دریافت تعداد ترددهای اشتراک: {e}")
        return {}

def predict_churn_risk(club_id):
    """محاسبه دقیق ریسک ریزش اعضا با تطابق استاندارد کلیدها و تاریخ‌ها"""
    try:
        raw_members = get_active_members(club_id)
        if not raw_members:
            return pd.DataFrame()
            
        df_members = pd.DataFrame(raw_members)
        
        attendance_logs = get_attendance_logs(club_id)
        last_checkin_map = {}
        if attendance_logs:
            df_att = pd.DataFrame(attendance_logs)
            if 'check_in_time' in df_att.columns and not df_att.empty:
                df_att['check_in_time'] = parse_to_tehran(df_att['check_in_time'])
                df_att = df_att.dropna(subset=['check_in_time'])
                for _, att_row in df_att.iterrows():
                    m_key = clean_id(att_row.get('member_id', att_row.get('id', '')))
                    c_time = att_row.get('check_in_time')
                    if m_key and (m_key not in last_checkin_map or c_time > last_checkin_map[m_key]):
                        last_checkin_map[m_key] = c_time

        sub_checkins = get_subscription_checkin_counts(club_id)
        now_tehran = pd.Timestamp.now(tz=TEHRAN_TZ_STR)
        
        # ۱. محاسبه روزهای غیبت
        def calc_days_absent(row):
            try:
                m_id = clean_id(row.get('id', row.get('member_id', '')))

                if m_id and m_id in last_checkin_map:
                    last_t = last_checkin_map[m_id]
                    if pd.notna(last_t):
                        diff = (now_tehran - last_t).days
                        return max(0, int(diff))
                
                join_date_val = row.get('join_date')
                if join_date_val:
                    join_dt = pd.to_datetime(join_date_val, errors='coerce')
                    if pd.notna(join_dt):
                        if join_dt.tzinfo is None:
                            join_dt = join_dt.tz_localize(TEHRAN_TZ_STR)
                        else:
                            join_dt = join_dt.tz_convert(TEHRAN_TZ_STR)
                        diff = (now_tehran - join_dt).days
                        return max(0, int(diff))

                return 0
            except Exception:
                return 0

        df_members['days_since_last_checkin'] = df_members.apply(calc_days_absent, axis=1)
        
        # ۲. محاسبه نمره ریسک ریزش
        def calculate_risk_score(row):
            try:
                days = row.get('days_since_last_checkin', 0)
                if pd.isna(days):
                    days = 0

                remaining = row.get('subscription_days', row.get('remaining_sessions', 0))
                if pd.isna(remaining) or remaining is None:
                    remaining = 0
                else:
                    remaining = float(remaining)

                sub_id_key = clean_id(row.get('subscription_id'))
                used_sessions = sub_checkins.get(sub_id_key, 0) if sub_id_key else 0
                calculated_total = remaining + used_sessions
                
                total_sessions = 24.0 if calculated_total > 12 else 12.0
                
                expected_rate = total_sessions / 30.0
                s_absence = days * expected_rate * 15.0
                
                progress = 1.0 - (remaining / total_sessions)
                progress = max(0.0, min(1.0, progress))
                s_lifecycle = 30.0 * (progress ** 2)
                
                total_score = min(100.0, s_absence + s_lifecycle)
                return round(float(total_score), 1)
            except Exception:
                return 0.0

        df_members['churn_risk_score'] = df_members.apply(calculate_risk_score, axis=1)
        
        # ۳. دسته‌بندی ریسک
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