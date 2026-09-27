import pandas as pd
import numpy as np

def run_full_analytics(df_members: pd.DataFrame, df_checkins: pd.DataFrame):
    """
    اجرای منطق ۶ بخش هوش مصنوعی روی داده‌های ورودی
    """
    if df_members.empty:
        return None

    # ترامپ/ترکیب داده‌ها
    df = df_members.copy()
    
    # ۱. بخش اول: شاخص‌های کلیدی عملکرد (KPIs)
    total_members = len(df)
    active_members = len(df[df['status'] == 'Active']) if 'status' in df.columns else total_members
    
    # ۲. بخش دوم: تحلیل و پیش‌بینی ریسک ریزش (Churn Risk Analysis)
    # بر اساس تعداد ترددها یا روزهای گذشته از آخرین حضور
    if 'checkin_count' not in df.columns and not df_checkins.empty:
        checkin_counts = df_checkins.groupby('member_id').size().reset_index(name='checkin_count')
        df = pd.merge(df, checkin_counts, left_on='id', right_on='member_id', how='left')
        df['checkin_count'] = df['checkin_count'].fillna(0)

    # الگوریتم سنجش ریسک
    def calculate_risk(row):
        count = row.get('checkin_count', 0)
        if count < 4:
            return 'High Risk'
        elif 4 <= count <= 10:
            return 'Medium Risk'
        return 'Low Risk'

    df['risk_level'] = df.apply(calculate_risk, axis=1)
    
    high_risk_df = df[df['risk_level'] == 'High Risk']
    churn_rate = round((len(high_risk_df) / total_members) * 100, 1) if total_members > 0 else 0

    # ۳. بخش سوم: تحلیل الگوهای تردد (Check-in Patterns)
    avg_checkins = round(df['checkin_count'].mean(), 1) if 'checkin_count' in df.columns else 0

    # ۴. بخش چهارم: سگمنت‌بندی هوشمند اعضا (Segmentation)
    high_risk_count = len(df[df['risk_level'] == 'High Risk'])
    med_risk_count = len(df[df['risk_level'] == 'Medium Risk'])
    low_risk_count = len(df[df['risk_level'] == 'Low Risk'])

    # ۵. بخش پنجم: شبیه‌سازی سناریوی بازگشت (Retention Simulation)
    # تخمین اثرگذاری کمپین‌های پیشنهادی
    estimated_recovered = int(high_risk_count * 0.35)  # فرض بازگشت ۳۵ درصد با مداخله هوش مصنوعی

    # ۶. بخش ششم: پیشنهادها و اکشن‌پلن عملیاتی (AI Action Plan)
    recommendations = []
    if high_risk_count > 0:
        recommendations.append(f"ارسال پیامک تخفیف تمدید برای {high_risk_count} عضو در معرض خطر ریزش شدید.")
    if avg_checkins < 5:
        recommendations.append("برگزاری برنامه‌های انگیزشی یا مربی خصوصی برای افزایش میانگین تردد هفته.")
    if not recommendations:
        recommendations.append("وضعیت تردد و ماندگاری اعضا در سطح مطلوب قرار دارد.")

    return {
        "total_members": total_members,
        "active_members": active_members,
        "churn_rate": churn_rate,
        "avg_checkins": avg_checkins,
        "high_risk_df": high_risk_df,
        "segmentation": {
            "High Risk": high_risk_count,
            "Medium Risk": med_risk_count,
            "Low Risk": low_risk_count
        },
        "simulation": {
            "current_high_risk": high_risk_count,
            "estimated_recovered": estimated_recovered,
            "projected_high_risk": high_risk_count - estimated_recovered
        },
        "recommendations": recommendations,
        "full_df": df
    }