import streamlit as st
import pandas as pd
from db_manager import get_members_data, get_checkins_data
from ai_analytics import run_full_analytics

st.set_page_config(page_title="سامانه هوشمند مدیریت و تحلیل باشگاه", layout="wide")

st.title("🏋️‍♂️ داشبورد هوشمند مدیریت اعضا و پیش‌بینی ریزش")

# دریافت داده‌ها از دیتابیس آنلاین
with st.spinner("در حال دریافت اطلاعات از دیتابیس آنلاین..."):
    df_members = get_members_data()
    df_checkins = get_checkins_data()

if df_members.empty:
    st.warning("داده‌ای در دیتابیس یافت نشد یا خطا در اتصال وجود دارد.")
else:
    # اجرای منطق هوش مصنوعی
    results = run_full_analytics(df_members, df_checkins)

    # تب‌بندی ۶ بخش هوش مصنوعی
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 ۱. شاخص‌های کلی",
        "⚠️ ۲. ریسک ریزش",
        "🗓️ ۳. الگوی تردد",
        "🎯 ۴. سگمنت‌بندی",
        "🔮 ۵. شبیه‌سازی بازگشت",
        "💡 ۶. پیشنهادهای AI"
    ])

    # بخش ۱: شاخص‌های کلی
    with tab1:
        st.header("خلاصه وضعیت باشگاه")
        col1, col2, col3 = st.columns(3)
        col1.metric("کل اعضا", results["total_members"])
        col2.metric("اعضای فعال", results["active_members"])
        col3.metric("نرخ ریزش (Churn Rate)", f"{results['churn_rate']}%")

    # بخش ۲: ریسک ریزش
    with tab2:
        st.header("اعضای در معرض خطر ریزش بالا")
        st.dataframe(
            results["high_risk_df"][['id', 'name', 'phone', 'checkin_count', 'risk_level']] 
            if 'name' in results["high_risk_df"].columns else results["high_risk_df"],
            use_container_width=True
        )

    # بخش ۳: الگوی تردد
    with tab3:
        st.header("تحلیل وضعیت حضور و غیاب")
        st.metric("میانگین تعداد تردد هر عضو", results["avg_checkins"])
        st.bar_chart(results["full_df"]['checkin_count'].value_counts())

    # بخش ۴: سگمنت‌بندی
    with tab4:
        st.header("دسته‌بندی سطح ریسک اعضا")
        seg_df = pd.DataFrame(list(results["segmentation"].items()), columns=['سطح ریسک', 'تعداد'])
        st.dataframe(seg_df, use_container_width=True)

    # بخش ۵: شبیه‌سازی سناریو
    with tab5:
        st.header("شبیه‌سازی کمپین‌های حفظ مشتری")
        col1, col2 = st.columns(2)
        col1.metric("تعداد اعضای پرریسک فعلی", results["simulation"]["current_high_risk"])
        col2.metric("تخمین بازگشت پس از پیامک انگیزشی", results["simulation"]["estimated_recovered"])

    # بخش ۶: پیشنهادها
    with tab6:
        st.header("توصیه‌های هوشمند جهت بهبود عملکرد")
        for rec in results["recommendations"]:
            st.info(f"📌 {rec}")