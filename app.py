import streamlit as st
import pandas as pd
import time
from datetime import datetime

from db_manager import (
    add_member, 
    get_all_members, 
    update_subscription, 
    decrement_subscription,
    clear_member_subscription,
    delete_member, 
    record_attendance,
    get_attendance_logs,
    reset_club_data
)
from ai_analytics import (
    get_hourly_occupancy, 
    predict_churn_risk, 
    get_subscription_checkin_counts
)
from auth_ui import render_auth_page
from ui_styles import FONT_STYLE
from panel_ui import render_sidebar, render_dashboard
from member_ui import render_add_member
from checkin_ui import render_checkin
from assign_ui import render_assign

st.set_page_config(page_title="سامانه مدیریت هوشمند باشگاه", page_icon="🏋️", layout="wide")

# -------------------------------------------------------------
# استایل RTL استاندارد + تنظیم عرض سایبار
# -------------------------------------------------------------
st.markdown(FONT_STYLE, unsafe_allow_html=True)
st.markdown("""
    <style>
    /* ۱. جهت‌‌دهی راست‌چین سراسری برای کل اپلیکیشن */
    html, body, .stApp {
        direction: rtl !important;
        text-align: right !important;
        font-family: 'Vazirmatn', 'Tahoma', sans-serif !important;
    }

    /* ۲. حذف کامل و قطعی متون عمودی سایبار هنگام بسته بودن */
    [data-testid="stSidebar"][aria-expanded="false"] * {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
    }

    /* ۳. تنظیم محتوای اصلی جهت عدم تداخل با لبه‌ها */
    .main .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        padding-right: 2rem !important;
        padding-left: 2rem !important;
        max-width: 100% !important;
    }

    /* ۴. تنظیم جهت و افزایش عرض سایبار در حالت باز */
    [data-testid="stSidebar"] {
        direction: rtl !important;
        text-align: right !important;
    }

    [data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 340px !important;
        max-width: 360px !important;
    }

    /* ۵. راست‌چین کردن ورودی‌ها، تب‌ها و دکمه‌ها */
    .stTextInput input, .stSelectbox, .stMarkdown, .stButton, div[data-baseweb="tab-list"] {
        direction: rtl !important;
        text-align: right !important;
    }

    div[data-baseweb="tab-list"] {
        justify-content: flex-start !important;
    }

    button[data-baseweb="tab"] {
        direction: rtl !important;
    }

    /* ۶. استایل تمیز جداول و کارت‌های متریک */
    [data-testid="stDataFrame"] {
        direction: rtl !important;
        background-color: #1e1e1e !important;
        border-radius: 8px !important;
        border: 1px solid #333333 !important;
    }

    [data-testid="stMetric"] {
        background-color: #262626 !important;
        border: 1px solid #3a3a3a !important;
        padding: 12px 16px !important;
        border-radius: 8px !important;
        text-align: right !important;
        direction: rtl !important;
    }

    [data-testid="stMetricLabel"] {
        color: #b0b0b0 !important;
        justify-content: flex-start !important;
        direction: rtl !important;
    }

    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 22px !important;
        font-weight: bold !important;
        text-align: right !important;
        direction: rtl !important;
    }

    .stButton > button {
        width: 100% !important;
        border-radius: 6px !important;
        font-weight: bold !important;
    }

    div[data-testid="InputInstructions"] {
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# مدیریت ماندگاری ورود کاربر در مرورگر
# -------------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'club_id' not in st.session_state:
    st.session_state.club_id = ""

query_params = st.query_params
if not st.session_state.logged_in and "session_club" in query_params:
    saved_club_id = query_params["session_club"]
    saved_username = query_params.get("session_user", "مدیر")
    if saved_club_id:
        st.session_state.logged_in = True
        st.session_state.club_id = saved_club_id
        st.session_state.username = saved_username

# -------------------------------------------------------------
# ۱. صفحه ورود و ثبت نام باشگاه
# -------------------------------------------------------------
if not st.session_state.logged_in:
    render_auth_page()

# -------------------------------------------------------------
# ۲. پنل اصلی سیستم (پس از ورود)
# -------------------------------------------------------------
else:
    welcome_msg = st.session_state.pop("welcome_toast", None)
    if welcome_msg:
        st.toast(welcome_msg, icon="👋")

    choice = render_sidebar()
    club_id = st.session_state.club_id

    # --- بخش ۱: مشاهده و جستجوی اعضا ---
    if choice == "داشبورد و اعضا":
        render_dashboard(club_id)

    # --- بخش ۲: ثبت عضو جدید ---
    elif choice == "ثبت عضو جدید":
        render_add_member(club_id)

    elif choice == "ثبت ورود (تردد)":
        render_checkin(club_id)

    # --- بخش ۴: تخصیص بسته ---
    elif choice == "تخصیص بسته":
        render_assign(club_id)

    elif choice == "📊 آمار و گزارشات":
        st.subheader("🤖 ماژول تحلیلی و پیش‌بینی هوشمند ریزش اعضا")
        
        hourly_df = get_hourly_occupancy(club_id)
        churn_df = predict_churn_risk(club_id)
        
        total_checkins = hourly_df['checkin_count'].sum() if not hourly_df.empty else 0
        if not hourly_df.empty and total_checkins > 0:
            peak_hour = hourly_df.loc[hourly_df['checkin_count'].idxmax()]['hour']
            peak_str = f"ساعت {peak_hour}:00"
        else:
            peak_str = "نامشخص"
            
        total_members = churn_df.shape[0] if not churn_df.empty else 0
        
        if total_members > 0:
            high_risk_cnt = churn_df[churn_df['risk_level'].str.contains('بالا|High', case=False, na=False)].shape[0]
            medium_risk_cnt = churn_df[churn_df['risk_level'].str.contains('متوسط|Medium', case=False, na=False)].shape[0]
            low_risk_cnt = churn_df[churn_df['risk_level'].str.contains('پایین|Low', case=False, na=False)].shape[0]
            
            high_pct = (high_risk_cnt / total_members) * 100
            med_pct = (medium_risk_cnt / total_members) * 100
            low_pct = (low_risk_cnt / total_members) * 100
        else:
            high_risk_cnt = medium_risk_cnt = low_risk_cnt = 0
            high_pct = med_pct = low_pct = 0.0

        m1, m2, m3, m4, m5 = st.columns(5)
        
        with m1:
            st.metric("مجموع ترددها", f"{total_checkins} ورود")
        with m2:
            st.metric("شلوغ‌ترین زمان", peak_str)
        with m3:
            st.metric("ریسک بالا 🔴", f"{high_risk_cnt} نفر", f"{high_pct:.1f}%")
        with m4:
            st.metric("ریسک متوسط 🟡", f"{medium_risk_cnt} نفر", f"{med_pct:.1f}%")
        with m5:
            st.metric("ریسک پایین 🟢", f"{low_risk_cnt} نفر", f"{low_pct:.1f}%")
        
        st.markdown("---")
        
        col_table, col_chart = st.columns([1, 1])
        
        with col_table:
            st.write("### ⚠️ پیش‌‌بینی ریسک ریزش اعضا (گزارش AI)")
            
            if not churn_df.empty:
                df_display = churn_df.copy()
                
                df_display = df_display.rename(columns={
                    'id': 'کد عضویت',
                    'name': 'نام ورزشکار',
                    'phone': 'شماره تماس',
                    'subscription_days': 'جلسات باقی‌مانده',
                    'days_since_last_checkin': 'مدت غیبت',
                    'churn_risk_score': 'نمره ریسک',
                    'risk_level': 'سطح ریسک'
                })
                
                if 'مدت غیبت' in df_display.columns:
                    df_display['مدت غیبت'] = df_display['مدت غیبت'].apply(
                        lambda x: "بدون تردد" if (pd.isna(x) or x == 30) else f"{int(x)} روز"
                    )

                display_cols = ['کد عضویت', 'نام ورزشکار', 'شماره تماس', 'جلسات باقی‌مانده', 'مدت غیبت', 'نمره ریسک', 'سطح ریسک']
                display_cols = [c for c in display_cols if c in df_display.columns]
                
                df_display = df_display[display_cols].sort_values(by='نمره ریسک', ascending=False)
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.info("هیچ داده‌ای برای تحلیل یافت نشد.")

        with col_chart:
            st.write("### 📈 تحلیل ساعات شلوغی باشگاه")
            if not hourly_df.empty:
                st.bar_chart(data=hourly_df, x='hour', y='checkin_count', color="#1f77b4")
            else:
                st.info("داده‌ای برای تحلیل تردد وجود ندارد.")

    # --- بخش ۶: مدیریت و حذف ---
    elif choice == "مدیریت و حذف":
        raw_members = get_all_members(club_id)

        st.subheader("👤 حذف دستی یک عضو مشخص")
        search_term = st.text_input("🔍 جستجوی عضو جهت حذف (بر اساس نام، شماره تماس یا کد ملی):")

        filtered_del = raw_members
        if search_term.strip():
            q = search_term.strip().lower()
            filtered_del = [
                m for m in raw_members
                if q in str(m.get("name", "")).lower()
                or q in str(m.get("phone", ""))
                or q in str(m.get("national_id", ""))
                or q in str(m.get("id", ""))
            ]

        if filtered_del:
            del_options = {
                f"کد: {m.get('id')} | {m.get('name')} | همراه: {m.get('phone')} | کد ملی: {m.get('national_id', 'نامشخص')}": m.get('id')
                for m in filtered_del
            }
            selected_option = st.selectbox("عضو مورد نظر را برای حذف انتخاب کنید:", list(del_options.keys()))
            selected_member_id = del_options[selected_option]

            if st.button("❌ حذف کامل عضو"):
                if delete_member(selected_member_id, club_id):
                    st.success("عضو مورد نظر با موفقیت حذف گردید.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("خطا در حذف عضو.")
        else:
            st.warning("هیچ عضوی با این مشخصات یافت نشد.")

        st.markdown("---")
        st.subheader("🗑 حذف اشتراک‌های اضافی (بدون حذف عضو)")

        sub_search_term = st.text_input("🔍 جستجوی عضو جهت مدیریت/حذف اشتراک (نام، شماره تماس یا کد ملی):", key="sub_search_input")

        filtered_sub = raw_members
        if sub_search_term.strip():
            q = sub_search_term.strip().lower()
            filtered_sub = [
                m for m in raw_members
                if q in str(m.get("name", "")).lower()
                or q in str(m.get("phone", ""))
                or q in str(m.get("national_id", ""))
                or q in str(m.get("id", ""))
            ]

        if filtered_sub:
            sub_member_options = {
                f"کد: {m.get('id')} | {m.get('name')} | همراه: {m.get('phone')}": m
                for m in filtered_sub
            }
            selected_sub_label = st.selectbox("عضو مورد نظر را انتخاب کنید:", list(sub_member_options.keys()))
            selected_sub_member = sub_member_options[selected_sub_label]
            m_id = selected_sub_member.get('id')
            sub_days = selected_sub_member.get('subscription_days', 0) or 0

            if sub_days > 0:
                package_desc = f"کد اشتراک: {m_id} | جلسات باقی‌مانده: {sub_days}"
                st.selectbox("اشتراکی که قصد حذف آن را دارید انتخاب کنید:", [package_desc])

                if st.button("❌ حذف این اشتراک"):
                    if clear_member_subscription(m_id, club_id):
                        st.success("اشتراک عضو با موفقیت صفر گردید.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("خطا در صفر کردن اشتراک.")
            else:
                st.info("این عضو در حال حاضر هیچ اشتراک فعال یا ثبت‌شده‌ای ندارد.")
        else:
            st.warning("هیچ عضوی با این مشخصات یافت نشد.")

        st.markdown("---")
        st.subheader("⚠️ ریست کامل دیتابیس (حذف تمامی اعضا و داده‌ها)")
        st.error("🚨 هشدار: این عملیات غیرقابل بازگشت است و تمام اعضا، اشتراک‌ها و ترددهای این باشگاه را کاملاً حذف می‌کند!")
        
        confirm_text = st.text_input("برای تایید، عبارت 'RESET' را به انگلیسی وارد کنید:")
        
        if st.button("🚨 تایید و شروع پاکسازی دیتابیس", type="primary"):
            if confirm_text.strip() == "RESET":
                st.session_state.reset_requested = True
            else:
                st.error("⚠️ برای تایید پاکسازی، باید دقیقاً عبارت RESET را به انگلیسی در کادر بالا وارد کنید.")

        if st.session_state.get('reset_requested', False):
            col_cancel, _ = st.columns([1, 2])
            with col_cancel:
                if st.button("❌ انصراف و لغو عملیات"):
                    st.session_state.reset_requested = False
                    st.info("عملیات پاکسازی با موفقیت لغو شد.")
                    time.sleep(1)
                    st.rerun()

            progress_bar = st.progress(100)
            status_text = st.empty()
            
            for i in range(5, 0, -1):
                if not st.session_state.get('reset_requested', False):
                    break
                status_text.warning(f"⚠️ پاکسازی دیتابیس تا {i} ثانیه دیگر انجام می‌شود... در صورت پشیمانی دکمه انصراف را بزنید!")
                progress_bar.progress(i * 20)
                time.sleep(1)
                
            if st.session_state.get('reset_requested', False):
                status_text.empty()
                progress_bar.empty()
                if reset_club_data(club_id):
                    st.session_state.reset_requested = False
                    st.success("🎉 تمامی داده‌های این باشگاه با موفقیت پاک شدند.")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("خطا در ریست دیتابیس.")