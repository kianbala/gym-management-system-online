import pandas as pd
from datetime import datetime
from db_manager import supabase

def get_hourly_occupancy(club_id):
    """محاسبه ساعات شلوغی باشگاه بر اساس تردد اعضا (club_id)"""
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
        # تبدیل تاریخ به حالت Naive بدون Timezone جهت جلوگیری از خطاهای محاسباتی
        df['check_in_time'] = pd.to_datetime(df['check_in_time']).dt.tz_localize(None)
        df['hour'] = df['check_in_time'].dt.hour
        
        hourly_counts = df.groupby('hour').size().reset_index(name='checkin_count')
        hourly_counts = hourly_counts.sort_values(by='hour').reset_index(drop=True)
        return hourly_counts
    except Exception as e:
        return pd.DataFrame(columns=['hour', 'checkin_count'])

def predict_churn_risk(club_id):
    """
    شناسایی اعضای در معرض ریزش بر اساس club_id.
    ابتدا سعی می‌کند داده‌ها را از نمای تحلیلی دیتابیس (vw_memberchurnanalytics) دریافت کند،
    در غیر این صورت محاسبات را به‌صورت مستقیم در پایتون انجام می‌دهد.
    """
    try:
        # ۱. تلاش برای دریافت داده از SQL View در صورت وجود در دیتابیس
        try:
            view_res = (
                supabase.table("vw_memberchurnanalytics")
                .select("*")
                .eq("club_id", club_id)
                .execute()
            )
            if view_res.data and len(view_res.data) > 0:
                return pd.DataFrame(view_res.data)
        except Exception:
            pass  # در صورت عدم وجود View، به بخش محاسبه مستقیم پایتون منتقل می‌شود

        # ۲. محاسبه مستقیم در پایتون
        members_res = (
            supabase.table("members")
            .select("id, name, phone, join_date")
            .eq("club_id", club_id)
            .execute()
        )
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
        
        # نگاشت آخرین تردد به هر عضو
        last_checkin_map = {}
        for log in attendance:
            m_id = log.get('member_id')
            if m_id and m_id not in last_checkin_map:
                try:
                    dt_val = pd.to_datetime(log['check_in_time'])
                    if hasattr(dt_val, 'tz_localize') and dt_val.tzinfo is not None:
                        dt_val = dt_val.tz_localize(None)
                    last_checkin_map[m_id] = dt_val
                except Exception:
                    pass

        now = datetime.now()
        churn_data = []

        for m in members:
            m_id = m['id']
            if m_id in last_checkin_map:
                days_absent = (now - last_checkin_map[m_id]).days
            else:
                join_str = m.get('join_date')
                if join_str:
                    try:
                        join_dt = datetime.strptime(join_str, "%Y-%m-%d")
                        days_absent = (now - join_dt).days
                    except Exception:
                        days_absent = 30
                else:
                    days_absent = 30

            days_absent = max(0, days_absent)

            # تعیین سطح ریسک همگام با بخش تحلیلی app.py
            if days_absent >= 20:
                risk_level = "🔴 ریسک بالا"
            elif days_absent >= 10:
                risk_level = "🟡 ریسک متوسط"
            else:
                risk_level = "🟢 پایین (Low)"

            churn_data.append({
                'id': m_id,
                'member_id': m_id,
                'name': m.get('name', '-'),
                'phone': m.get('phone', '-'),
                'days_since_last_checkin': days_absent,
                'days_absent': days_absent,
                'risk_level': risk_level
            })

        df_churn = pd.DataFrame(churn_data)
        return df_churn

    except Exception as e:
        return pd.DataFrame()