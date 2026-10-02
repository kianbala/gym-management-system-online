import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from db_manager import get_active_members, get_attendance_logs

warnings.filterwarnings('ignore', category=UserWarning)

def get_hourly_occupancy(club_id):
    """تحلیل و استخراج میزان شلوغی باشگاه بر اساس ساعات شبانه‌روز"""
    try:
        logs = get_attendance_logs(club_id)
        if not logs:
            return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})
        
        df = pd.DataFrame(logs)
        df['checkin_datetime'] = pd.to_datetime(df['check_in_time'])
        df['hour'] = df['checkin_datetime'].dt.hour
        
        hourly_counts = df.groupby('hour').size().reset_index(name='checkin_count')
        
        all_hours = pd.DataFrame({'hour': list(range(0, 24))})
        result = pd.merge(all_hours, hourly_counts, on='hour', how='left').fillna(0)
        result['checkin_count'] = result['checkin_count'].astype(int)
        
        return result
    except Exception as e:
        print(f"⚠️ خطا در محاسبه ساعات شلوغی: {e}")
        return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})

def predict_churn_risk(club_id):
    """تحلیل ریسک ریزش اعضا بر اساس مدل اول (ترکیب شدت غیبت بر اساس نوع بسته + وزن درجه دو پایان بسته)"""
    try:
        raw_members = get_active_members(club_id)
        if not raw_members:
            return pd.DataFrame()
            
        df_members = pd.DataFrame(raw_members)
        
        attendance_logs = get_attendance_logs(club_id)
        last_checkin_map = {}
        if attendance_logs:
            df_att = pd.DataFrame(attendance_logs)
            df_att['check_in_time'] = pd.to_datetime(df_att['check_in_time'])
            last_att = df_att.groupby('member_id')['check_in_time'].max().to_dict()
            last_checkin_map = last_att

        now = datetime.now()
        
        # ۱. محاسبه روزهای غیبت
        def calc_days_absent(row):
            m_id = row['id']
            if m_id in last_checkin_map:
                last_t = last_checkin_map[m_id]
                if hasattr(last_t, 'tzinfo') and last_t.tzinfo is not None:
                    last_t = last_t.tz_localize(None)
                diff = (now - last_t).days
                return max(0, diff)
            return 15  # پیش‌فرض برای افرادی که هنوز هیچ ترودی ثبت نکرده‌اند

        df_members['days_since_last_checkin'] = df_members.apply(calc_days_absent, axis=1)
        
        # ۲. محاسبه نمره ریسک طبق فرمول مدل اول
        def calculate_risk_score(row):
            days = row['days_since_last_checkin']
            sessions = row.get('subscription_days', 0) or 0
            
            # تشخیص نوع بسته (اگر بیش از ۱۲ جلسه داشته باشد ۲۴ جلسه‌ای، در غیر این صورت ۱۲ جلسه‌ای)
            total_sessions = 24 if sessions > 12 else 12
            
            # الف) محاسبه شدت غیبت متناسب با نرخ انتظار بسته
            expected_rate = total_sessions / 30.0  # 0.8 برای 24 جلسه و 0.4 برای 12 جلسه
            s_absence = days * expected_rate * 15.0
            
            # ب) محاسبه وزن پایان بسته (تابع درجه دو)
            progress = 1.0 - (sessions / float(total_sessions))
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