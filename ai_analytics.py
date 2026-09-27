import pandas as pd
from datetime import datetime
from db_manager import supabase

def get_hourly_occupancy(club_id):
    """محاسبه ساعات شلوغی باشگاه بر اساس club_id"""
    try:
        res = (
            supabase.table("attendance")
            .select("check_in_time")
            .eq("club_id", club_id)
            .execute()
        )
        data = res.data if res.data else []
        
        if not data:
            return pd.DataFrame(columns=['hour', 'checkin_count'])
        
        df = pd.DataFrame(data)
        df['check_in_time'] = pd.to_datetime(df['check_in_time'])
        df['hour'] = df['check_in_time'].dt.hour
        
        hourly_counts = df.groupby('hour').size().reset_index(name='checkin_count')
        return hourly_counts
    except Exception as e:
        return pd.DataFrame(columns=['hour', 'checkin_count'])

def predict_churn_risk(club_id):
    """شناسایی اعضای در معرض ریزش بر اساس club_id"""
    try:
        # ۱. دریافت لیست اعضای باشگاه
        members_res = (
            supabase.table("members")
            .select("id, name, phone")
            .eq("club_id", club_id)
            .execute()
        )
        members = members_res.data if members_res.data else []
        if not members:
            return pd.DataFrame()

        # ۲. دریافت آخرین تاریخ تردد اعضا
        attendance_res = (
            supabase.table("attendance")
            .select("member_id, check_in_time")
            .eq("club_id", club_id)
            .order("check_in_time", desc=True)
            .execute()
        )
        attendance = attendance_res.data if attendance_res.data else []
        
        # نگاشت آخرین تردد به هر عضو
        last_checkin_map = {}
        for log in attendance:
            m_id = log['member_id']
            if m_id not in last_checkin_map:
                # تبدیل تاریخ تردد به حالت Naive بدون Timezone
                dt_val = pd.to_datetime(log['check_in_time'])
                if hasattr(dt_val, 'tz_localize') and dt_val.tzinfo is not None:
                    dt_val = dt_val.tz_localize(None)
                last_checkin_map[m_id] = dt_val

        now = datetime.now()
        churn_data = []

        for m in members:
            m_id = m['id']
            if m_id in last_checkin_map:
                days_absent = (now - last_checkin_map[m_id]).days
            else:
                days_absent = 30  # اگر تردد نداشته، ۳۰ روز غیبت فرض می‌شود

            if days_absent >= 14:
                risk_level = "🔴 ریسک بالا"
            elif days_absent >= 7:
                risk_level = "🟡 ریسک متوسط"
            else:
                risk_level = "🟢 فعال (کم‌ریسک)"

            churn_data.append({
                'name': m['name'],
                'phone': m['phone'],
                'days_since_last_checkin': days_absent,
                'risk_level': risk_level
            })

        df_churn = pd.DataFrame(churn_data)
        return df_churn[df_churn['days_since_last_checkin'] >= 7]

    except Exception as e:
        return pd.DataFrame()