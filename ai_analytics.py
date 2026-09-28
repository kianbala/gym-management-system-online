import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from db_manager import get_all_members, get_attendance_logs

warnings.filterwarnings('ignore', category=UserWarning)

def get_hourly_occupancy(club_id: str):
    """تحلیل و استخراج میزان شلوغی باشگاه بر اساس ساعات شبانه‌روز برای یک باشگاه مشخص"""
    try:
        attendance_logs = get_attendance_logs(club_id)
        
        if not attendance_logs:
            return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0] * 24})
        
        df = pd.DataFrame(attendance_logs)
        df['checkin_datetime'] = pd.to_datetime(df['check_in_time'], utc=True)
        df['hour'] = df['checkin_datetime'].dt.hour
        
        hourly_counts = df.groupby('hour').size().reset_index(name='checkin_count')
        
        all_hours = pd.DataFrame({'hour': list(range(0, 24))})
        result = pd.merge(all_hours, hourly_counts, on='hour', how='left').fillna(0)
        result['checkin_count'] = result['checkin_count'].astype(int)
        
        return result
    except Exception:
        return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0] * 24})


def predict_churn_risk(club_id: str):
    """
    تحلیل هوشمند ریسک ریزش اعضا (ترکیب روزهای غیبت + جلسات باقی‌مانده)
    سازگار با سیستم دو مرحله‌ای (اعضای بدون بسته و اعضای دارای اشتراک)
    """
    try:
        raw_members = get_all_members(club_id)
        attendance_logs = get_attendance_logs(club_id)
        
        if not raw_members:
            return pd.DataFrame()
        
        # استخراج جدیدترین (آخرین) زمان حضور هر عضو به صورت ایمن و بدون تداخل Timezone
        last_checkin_map = {}
        for log in attendance_logs:
            m_id = log.get('member_id')
            check_time_str = log.get('check_in_time')
            if m_id and check_time_str:
                try:
                    dt = pd.to_datetime(check_time_str, utc=True).tz_localize(None)
                    # اگر عضو در مپ نباشد یا این تاریخ جدیدتر از قبلی باشد، به‌روزرسانی می‌شود
                    if m_id not in last_checkin_map or dt > last_checkin_map[m_id]:
                        last_checkin_map[m_id] = dt
                except Exception:
                    pass

        now = datetime.now()
        processed_members = []

        for m in raw_members:
            m_id = m.get('id')
            name = m.get('name', '')
            phone = m.get('phone', '')
            sessions = m.get('subscription_days', 0) or 0
            join_date_str = m.get('join_date')

            # ۱. محاسبه روزهای غیبت
            if m_id in last_checkin_map:
                last_dt = last_checkin_map[m_id]
                days_absent = max(0, (now - last_dt).days)
            elif join_date_str:
                try:
                    join_dt = datetime.strptime(join_date_str, "%Y-%m-%d")
                    days_absent = max(0, (now - join_dt).days)
                except Exception:
                    days_absent = 30
            else:
                days_absent = 30

            # ۲. محاسبه امتیاز هوشمند ریسک
            # تاثیر روزهای غیبت (تا سقف ۷۰ امتیاز)
            risk_from_days = min(days_absent * 5, 70)

            # تاثیر جلسات رو به اتمام (تا سقف ۳۰ امتیاز)
            if sessions == 0:
                risk_from_sessions = 30
            elif sessions <= 3:
                risk_from_sessions = 15
            else:
                risk_from_sessions = 0

            churn_risk_score = float(risk_from_days + risk_from_sessions)

            # ۳. تبدیل امتیاز عددی به برچسب
            if churn_risk_score >= 70:
                risk_level = 'بالا (High)'
            elif churn_risk_score >= 40:
                risk_level = 'متوسط (Medium)'
            else:
                risk_level = 'پایین (Low)'

            processed_members.append({
                'id': m_id,
                'member_id': m_id,
                'name': name,
                'phone': phone,
                'remaining_sessions': sessions,
                'days_since_last_checkin': days_absent,
                'days_absent': days_absent,
                'churn_risk_score': churn_risk_score,
                'risk_level': risk_level
            })

        df = pd.DataFrame(processed_members)
        return df

    except Exception:
        return pd.DataFrame()