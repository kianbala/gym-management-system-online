import pandas as pd
from datetime import datetime
from db_manager import supabase

def get_hourly_occupancy(club_id):
    """محاسبه نمودار شلوغی باشگاه"""
    try:
        res = supabase.table("attendance").select("check_in_time").eq("club_id", club_id).execute()
        data = res.data if res.data else []
        
        if not data:
            return pd.DataFrame(columns=['hour', 'checkin_count'])
        
        df = pd.DataFrame(data)
        df['check_in_time'] = pd.to_datetime(df['check_in_time'])
        df['hour'] = df['check_in_time'].dt.hour
        
        return df.groupby('hour').size().reset_index(name='checkin_count')
    except Exception:
        return pd.DataFrame(columns=['hour', 'checkin_count'])

def predict_churn_risk(club_id):
    """محاسبه امتیاز ریسک ریزش اعضا (۰ تا ۱۰۰) شبیه کد لوکال"""
    try:
        members_res = supabase.table("members").select("*").eq("club_id", club_id).execute()
        members = members_res.data if members_res.data else []
        if not members:
            return pd.DataFrame()

        attendance_res = (
            supabase.table("attendance")
            .select("member_id, check_in_time")
            .eq("club_id", club_id)
            .order("check_in_time", desc=True)
            .execute()
        )
        attendance = attendance_res.data if attendance_res.data else []
        
        last_checkin_map = {}
        for log in attendance:
            m_id = log['member_id']
            if m_id not in last_checkin_map:
                last_checkin_map[m_id] = pd.to_datetime(log['check_in_time'])

        now = datetime.now()
        churn_data = []

        for m in members:
            m_id = m['id']
            days_absent = (now - last_checkin_map[m_id].replace(tzinfo=None)).days if m_id in last_checkin_map else 30
            sessions_left = m.get('sessions_left', 0)
            sub_days = m.get('subscription_days', 0)

            # فرمول دقیق لوکال برای محاسبه Churn Score (۰ تا ۱۰۰)
            absence_score = min(days_absent * 4, 60)
            session_score = 20 if sessions_left <= 2 else 0
            day_score = 20 if sub_days <= 5 else 0
            
            churn_score = absence_score + session_score + day_score

            if churn_score >= 70:
                risk_level = "🔴 ریسک بسیار بالا"
            elif churn_score >= 40:
                risk_level = "🟡 ریسک متوسط"
            else:
                risk_level = "🟢 فعال / کم‌ریسک"

            churn_data.append({
                'name': m['name'],
                'phone': m['phone'],
                'days_absent': days_absent,
                'sessions_left': sessions_left,
                'sub_days': sub_days,
                'churn_score': churn_score,
                'risk_level': risk_level
            })

        df_churn = pd.DataFrame(churn_data)
        return df_churn.sort_values(by='churn_score', ascending=False)

    except Exception:
        return pd.DataFrame()