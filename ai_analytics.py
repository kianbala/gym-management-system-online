import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from db_manager import supabase

warnings.filterwarnings('ignore', category=UserWarning)

def get_hourly_occupancy(club_id):
    """تحلیل و استخراج میزان شلوغی باشگاه بر اساس ساعات شبانه‌روز برای یک باشگاه مشخص"""
    try:
        res = supabase.table("attendance").select("check_in_time").eq("club_id", club_id).execute()
        data = res.data or []
        
        if not data:
            return pd.DataFrame({'hour': list(range(0, 24)), 'checkin_count': [0]*24})
        
        df = pd.DataFrame(data)
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
    """
    تحلیل ریسک ریزش اعضا بر اساس منطق دقیق کد لوکال
    (ترکیب روزهای غیبت + جلسات رو به اتمام)
    """
    try:
        # ۱. دریافت لیست اعضای باشگاه
        members_res = supabase.table("members").select("*").eq("club_id", club_id).execute()
        members_data = members_res.data or []
        
        if not members_data:
            return pd.DataFrame()
            
        df_members = pd.DataFrame(members_data)
        
        # ۲. دریافت آخرین تاریخ تردد اعضا
        attendance_res = supabase.table("attendance").select("member_id, check_in_time").eq("club_id", club_id).execute()
        attendance_data = attendance_res.data or []
        
        last_checkin_map = {}
        if attendance_data:
            df_att = pd.DataFrame(attendance_data)
            df_att['check_in_time'] = pd.to_datetime(df_att['check_in_time'])
            # پیدا کردن آخرین زمان حضور برای هر کاربر
            last_att = df_att.groupby('member_id')['check_in_time'].max().to_dict()
            last_checkin_map = last_att

        now = datetime.now()
        
        # ۳. محاسبه روزهای غیبت
        def calc_days_absent(row):
            m_id = row['id']
            if m_id in last_checkin_map:
                last_t = last_checkin_map[m_id]
                # تبدیل به حالت tz-naive جهت مقایسه بدون خطا
                if hasattr(last_t, 'tzinfo') and last_t.tzinfo is not None:
                    last_t = last_t.tz_localize(None)
                diff = (now - last_t).days
                return max(0, diff)
            return 30  # اگر ترددی ثبت نشده، طبق منطق لوکال ۳۰ روز در نظر گرفته می‌شود

        df_members['days_since_last_checkin'] = df_members.apply(calc_days_absent, axis=1)
        
        # ۴. محاسبه دقیق امتیاز ریسک طبق فرمول لوکال (0 تا 100)
        def calculate_risk_score(row):
            days = row['days_since_last_checkin']
            sessions = row.get('subscription_days', 0) or 0
            
            # تاثیر روزهای غیبت (تا سقف ۷۰ امتیاز)
            risk_from_days = min(days * 5, 70)
            
            # تاثیر جلسات رو به اتمام (تا سقف ۳۰ امتیاز)
            if sessions <= 0:
                risk_from_sessions = 30
            elif sessions <= 3:
                risk_from_sessions = 15
            else:
                risk_from_sessions = 0
                
            return float(risk_from_days + risk_from_sessions)

        df_members['churn_risk_score'] = df_members.apply(calculate_risk_score, axis=1)
        
        # ۵. نگاشت امتیاز به برچسب سطح ریسک
        def map_to_label(score):
            if score >= 70:
                return 'بالا (High)'
            elif score >= 40:
                return 'متوسط (Medium)'
            else:
                return 'پایین (Low)'
                
        df_members['risk_level'] = df_members['churn_risk_score'].apply(map_to_label)
        
        return df_members

    except Exception as e:
        print(f"⚠️ خطا در محاسبه پیش‌بینی ریزش: {e}")
        return pd.DataFrame()