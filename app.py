import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta

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
from ai_analytics import get_hourly_occupancy, predict_churn_risk
from auth import authenticate_user, add_user

st.set_page_config(page_title="سامانه مدیریت هوشمند باشگاه", layout="wide")

# -------------------------------------------------------------
# استایل RTL استاندارد و تنظیم عرض سایبار
# -------------------------------------------------------------
st.markdown("""
    <style>
    /* ۱. جهت‌دهی راست‌‌چین سراسری برای کل اپلیکیشن */
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

    /* ۴. تنظیم عرض پایه سایبار و امکان تغییر اندازه دستی (Drag & Resize) */
    [data-testid="stSidebar"] {
        direction: rtl !important;
        text-align: right !important;
        min-width: 280px !important;
        resize: horizontal !important;
        overflow: auto !important;
    }

    /* جلوگیری از شکستن متون منو */
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] {
        white-space: nowrap !important;
    }

    /* ۵. راست‌‌چین کردن ورودی‌ها، تب‌ها و دکمه‌ها */
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
# ۱. صفحه ورود و ثبت‌نام باشگاه
# -------------------------------------------------------------
if not st.session_state.logged_in:
    st.subheader("🔑 ورود یا ثبت‌نام باشگاه")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔐 ورود به سیستم", "👤 ثبت‌نام باشگاه جدید"])
        
        with tab_login:
            with st.form("login_form"):
                username_input = st.text_input("نام کاربری")
                password_input = st.text_input("رمز عبور", type="password")
                submit_login = st.form_submit_button("ورود به سیستم", type="primary")
                
                if submit_login:
                    if username_input and password_input:
                        success, club_id = authenticate_user(username_input, password_input)
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.username = username_input
                            st.session_state.club_id = club_id
                            
                            st.query_params["session_club"] = club_id
                            st.query_params["session_user"] = username_input
                            
                            st.success(f"خوش آمدید {username_input}!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("نام کاربری یا رمز عبور اشتباه است.")
                    else:
                        st.warning("لطفاً اطلاعات را کامل وارد کنید.")
                        
        with tab_register:
            with st.form("register_form"):
                reg_username = st.text_input("نام کاربری مدیر")
                reg_club_name = st.text_input("نام باشگاه / شرکت")
                reg_password = st.text_input("رمز عبور", type="password")
                submit_reg = st.form_submit_button("ساخت حساب باشگاه جدید", type="primary")
                
                if submit_reg:
                    if reg_username.strip() and reg_password.strip() and reg_club_name.strip():
                        if add_user(reg_username, reg_password, club_name=reg_club_name):
                            st.success(f"باشگاه '{reg_club_name}' ایجاد شد! اکنون می‌توانید وارد شوید.")
                        else:
                            st.error("نام کاربری تکراری است.")
                    else:
                        st.warning("لطفاً تمامی فیلدها را پر کنید.")

# -------------------------------------------------------------
# ۲. پنل اصلی سیستم (پس از ورود)
# -------------------------------------------------------------
else:
    st.sidebar.write(f"👤 **مدیر:** {st.session_state.username}")
    st.sidebar.write(f"🏢 **باشگاه:** {st.session_state.club_id}")
    
    if st.sidebar.button("🚪 خروج"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.club_id = ""
        st.query_params.clear()
        st.rerun()

    st.sidebar.markdown("---")
    
    menu = [
        "داشبورد و اعضا", 
        "ثبت عضو جدید", 
        "ثبت ورود (تردد)", 
        "تخصیص بسته", 
        "📊 تحلیل و هوش مصنوعی", 
        "مدیریت و حذف"
    ]
    choice = st.sidebar.selectbox("منوی اصلی", menu)
    club_id = st.session_state.club_id

    # --- بخش ۱: مشاهده و جستجوی اعضا ---
    if choice == "داشبورد و اعضا":
        st.subheader("📋 لیست اعضا و وضعیت اشتراک‌ها")
        
        raw_members = get_all_members(club_id)
        attendance_logs = get_attendance_logs(club_id)
        
        last_checkin_map = {}
        for log in attendance_logs:
            m_id = log.get('member_id')
            check_time_str = log.get('check_in_time')
            if m_id and check_time_str and m_id not in last_checkin_map:
                try:
                    dt = datetime.fromisoformat(check_time_str.replace('Z', '+00:00'))
                    last_checkin_map[m_id] = dt.date()
                except Exception:
                    pass

        now_date = datetime.now().date()
        processed_data = []

        for m in raw_members:
            m_id = m.get("id")
            name = m.get("name", "")
            national_id = m.get("national_id", "")
            phone = m.get("phone", "")
            sub_days = m.get("subscription_days", 0) or 0
            join_date_str = m.get("join_date")

            if sub_days > 0:
                package_type = "بسته ۲ | ۲۴ جلسه" if sub_days > 12 else "بسته ۱ | ۱۲ جلسه"
                
                expire_str = "نامشخص"
                is_expired_by_time = False
                if join_date_str:
                    try:
                        clean_join = join_date_str.split('T')[0]
                        join_dt = datetime.strptime(clean_join, "%Y-%m-%d").date()
                        expire_dt = join_dt + timedelta(days=30)
                        expire_str = expire_dt.isoformat()
                        if now_date > expire_dt:
                            is_expired_by_time = True
                    except Exception:
                        pass

                status_str = "EXPIRED" if is_expired_by_time else "ACTIVE"
                sub_code = str(m_id)
                sessions_left = str(sub_days)
            else:
                package_type = "-"
                sub_code = "-"
                sessions_left = "-"
                expire_str = "-"
                status_str = "EXPIRED" if join_date_str else "فاقد اشتراک"

            if m_id in last_checkin_map:
                days_absent_val = (now_date - last_checkin_map[m_id]).days
                days_absent_str = f"{max(0, days_absent_val)} روز"
            else:
                days_absent_str = "بدون تردد"

            processed_data.append({
                "کد عضویت": m_id,
                "نام و نام خانوادگی": name,
                "کد ملی": national_id,
                "شماره تماس": phone,
                "نوع بسته": package_type,
                "کد اشتراک": sub_code,
                "جلسات باقی‌مانده": sessions_left,
                "تاریخ انقضا": expire_str,
                "وضعیت": status_str,
                "روزهای غیبت": days_absent_str
            })

        col_search, col_filter = st.columns([2, 1])
        
        with col_search:
            search_dash = st.text_input("🔍 جستجوی عضو (نام، شماره، کد ملی یا کد عضویت):", placeholder="مثلاً: علی، 0912 یا کد عضویت...")
            
        with col_filter:
            selected_status = st.selectbox("فیلتر وضعیت اشتراک:", ["همه", "ACTIVE", "EXPIRED"])

        filtered_list = processed_data
        if selected_status != "همه":
            filtered_list = [item for item in filtered_list if item["وضعیت"] == selected_status]

        if search_dash.strip():
            q = search_dash.strip().lower()
            filtered_list = [
                item for item in filtered_list
                if q in str(item["نام و نام خانوادگی"]).lower()
                or q in str(item["کد ملی"])
                or q in str(item["شماره تماس"])
                or q in str(item["کد عضویت"])
            ]

        st.caption(f"📊 تعداد اعضای یافت شده: **{len(filtered_list)} نفر**")

        if filtered_list:
            df_display = pd.DataFrame(filtered_list)
            cols_order = [
                "کد عضویت", "نام و نام خانوادگی", "کد ملی", "شماره تماس",
                "نوع بسته", "کد اشتراک", "جلسات باقی‌مانده", "تاریخ انقضا",
                "وضعیت", "روزهای غیبت"
            ]
            df_display = df_display[cols_order]
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("هیچ عضوی با این مشخصات یافت نشد.")

    # --- بخش ۲: ثبت عضو جدید ---
    elif choice == "ثبت عضو جدید":
        st.subheader("➕ ثبت عضو جدید")
        with st.form("add_member_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                first_name = st.text_input("نام")
                last_name = st.text_input("نام خانوادگی")
            with col2:
                national_id = st.text_input("کد ملی (۱۰ رقمی)")
                phone_number = st.text_input("شماره تماس (۱۱ رقمی)")
                
            submit = st.form_submit_button("ثبت عضو", type="primary")
            
            if submit:
                first_name_clean = first_name.strip()
                last_name_clean = last_name.strip()
                n_id = national_id.strip()
                ph = phone_number.strip()
                
                if first_name_clean and last_name_clean and n_id and ph:
                    if len(n_id) != 10 or not n_id.isdigit():
                        st.warning("⚠️ کد ملی باید دقیقاً ۱۰ رقم عددی باشد.")
                    elif len(ph) != 11 or not ph.isdigit():
                        st.warning("⚠️ شماره تماس باید دقیقاً ۱۱ رقم عددی باشد (مثلاً 09123456789).")
                    else:
                        full_name = f"{first_name_clean} {last_name_clean}"
                        success, msg = add_member(full_name, ph, n_id, club_id, subscription_days=0)
                        if success:
                            st.success(msg)
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.warning("لطفاً تمامی فیلدها را پر کنید.")

    # --- بخش ۳: ثبت ورود ---
    elif choice == "ثبت ورود (تردد)":
        st.subheader("🚪 ثبت ورود ورزشکار و کسر جلسه")
        
        raw_members = get_all_members(club_id)
        now_date = datetime.now().date()
        
        active_members = []
        for m in raw_members:
            sub_days = m.get("subscription_days", 0) or 0
            join_date_str = m.get("join_date")
            
            is_expired = False
            if join_date_str:
                try:
                    clean_join = join_date_str.split('T')[0]
                    join_dt = datetime.strptime(clean_join, "%Y-%m-%d").date()
                    if now_date > (join_dt + timedelta(days=30)):
                        is_expired = True
                except Exception:
                    pass
            
            if sub_days > 0 and not is_expired:
                active_members.append(m)
        
        search_input = st.text_input("🔍 جستجوی ورزشکار (نام، شماره تماس، کد ملی یا کد عضویت):", placeholder="مثلاً: علی، 0912 یا کد عضویت...")
        
        filtered_members = active_members
        if search_input.strip():
            q = search_input.strip().lower()
            filtered_members = [
                m for m in active_members
                if q in str(m.get("name", "")).lower()
                or q in str(m.get("phone", ""))
                or q in str(m.get("national_id", ""))
                or q in str(m.get("id", ""))
            ]
            
        if filtered_members:
            st.caption(f"🔍 تعداد {len(filtered_members)} مورد یافت شد:")
            
            options = {
                f"👤 {m.get('name', '')} | 📱 {m.get('phone', '')} | 🔢 باقی‌مانده: {m.get('subscription_days', 0)} جلسه (کد عضویت: {m.get('id')})": m
                for m in filtered_members
            }
            
            selected_label = st.selectbox("لیست افراد یافت‌شده:", list(options.keys()))
            selected_member = options[selected_label]
            member_id = selected_member.get('id')
            
            st.info(
                f"**عضو انتخاب‌شده:** {selected_member.get('name')}  \n"
                f"**جلسات باقی‌مانده فعلی:** {selected_member.get('subscription_days', 0)} جلسه"
            )
            
            if st.button("🟢 ثبت حضور (کاهش ۱ جلسه)", type="primary"):
                if record_attendance(member_id, club_id):
                    if decrement_subscription(member_id, club_id):
                        st.success("ورود با موفقیت ثبت شد و ۱ جلسه کسر گردید.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("ورود ثبت شد اما در کسر جلسه خطایی رخ داد.")
                else:
                    st.error("خطا در ثبت ورود.")
        else:
            st.warning("هیچ عضو فعالی با این مشخصات یافت نشد.")

    # --- بخش ۴: تخصیص بسته ---
    elif choice == "تخصیص بسته":
        st.subheader("💳 اختصاص بسته جدید به عضو")
        
        raw_members = get_all_members(club_id)
        now_date = datetime.now().date()

        search_input = st.text_input("🔍 جستجوی ورزشکار (نام، شماره تماس، کد ملی یا کد عضویت):", placeholder="مثلاً: حسین، 0912...", key="assign_search")

        filtered_members = raw_members
        if search_input.strip():
            q = search_input.strip().lower()
            filtered_members = [
                m for m in raw_members
                if q in str(m.get("name", "")).lower()
                or q in str(m.get("phone", ""))
                or q in str(m.get("national_id", ""))
                or q in str(m.get("id", ""))
            ]

        if filtered_members:
            st.caption(f"🔍 تعداد {len(filtered_members)} مورد یافت شد:")

            member_options = {}
            can_assign_map = {}

            for m in filtered_members:
                m_id = m.get("id")
                sub_days = m.get("subscription_days", 0) or 0
                join_date_str = m.get("join_date")

                is_expired = False
                if join_date_str:
                    try:
                        clean_join = join_date_str.split('T')[0]
                        join_dt = datetime.strptime(clean_join, "%Y-%m-%d").date()
                        if now_date > (join_dt + timedelta(days=30)):
                            is_expired = True
                    except Exception:
                        pass

                can_assign = (sub_days <= 0 or is_expired)
                status_text = "🟢 مجاز به تخصیص" if can_assign else f"🔴 دارای اشتراک فعال ({sub_days} جلسه)"
                
                label = f"👤 {m.get('name')} | 📱 {m.get('phone')} | 🆔 کد ملی: {m.get('national_id')} | {status_text}"
                member_options[label] = m_id
                can_assign_map[m_id] = can_assign

            selected_label = st.selectbox("انتخاب عضو:", list(member_options.keys()))
            selected_member_id = member_options[selected_label]
            can_assign = can_assign_map[selected_member_id]

            if can_assign:
                st.info("✅ این کاربر آماده ثبت بسته جدید است.")
            else:
                st.warning("⚠️ کاربر دارای اشتراک فعال است. تا زمانی که جلسات به اتمام نرسد یا ۳۰ روز منقضی نشود، امکان ثبت بسته جدید نیست.")

            packages = {
                "بسته ۱ | یک ماه ۱۲ جلسه | 800,000 تومان": 12,
                "بسته ۲ | یک ماه ۲۴ جلسه | 1,400,000 تومان": 24
            }

            selected_package_label = st.selectbox("انتخاب بسته ورزشی:", list(packages.keys()))
            sessions_to_add = packages[selected_package_label]

            if st.button("🟢 فعال‌‌سازی بسته", type="primary", disabled=not can_assign):
                if update_subscription(selected_member_id, sessions_to_add, club_id, overwrite=True):
                    st.success(f"بسته جدید ({sessions_to_add} جلسه) با موفقیت برای کاربر فعال گردید.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("خطا در اختصاص بسته.")
        else:
            st.warning("هیچ عضوی با این مشخصات یافت نشد.")

    # --- بخش ۵: تحلیل و هوش مصنوعی ---
    elif choice == "📊 تحلیل و هوش مصنوعی":
        st.subheader("🤖 ماژول تحلیلی و پیش‌‌بینی هوشمند ریزش اعضا")
        
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
            st.write("### ⚠️ پیش‌بینی ریسک ریزش اعضا (گزارش AI)")
            
            if not churn_df.empty:
                df_display = churn_df.copy()
                
                df_display = df_display.rename(columns={
                    'id': 'کد عضویت',
                    'name': 'نام ورزشکار',
                    'phone': 'شماره تماس',
                    'subscription_days': 'جلسات',
                    'days_since_last_checkin': 'غیبت',
                    'churn_risk_score': 'نمره ریسک',
                    'risk_level': 'سطح ریسک'
                })
                
                if 'غیبت' in df_display.columns:
                    df_display['غیبت'] = df_display['غیبت'].apply(
                        lambda x: "بدون تردد" if (pd.isna(x) or x == 30) else f"{int(x)} روز"
                    )

                display_cols = ['کد عضویت', 'نام ورزشکار', 'شماره تماس', 'جلسات', 'غیبت', 'نمره ریسک', 'سطح ریسک']
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
        st.subheader("⚠️️ ریست کامل دیتابیس (حذف تمامی اعضا و داده‌ها)")
        st.error("🚨 هشدار: این عملیات غیرقابل بازگشت است و تمام اعضا، اشتراک‌ها و ترددهای این باشگاه را کاملاً حذف می‌کند!")
        
        confirm_text = st.text_input("برای تایید، عبارت 'RESET' را به انگلیسی وارد کنید:")
        
        if confirm_text.strip() == "RESET":
            if 'reset_requested' not in st.session_state:
                st.session_state.reset_requested = False

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🚨 شروع پاکسازی (با مهلت ۵ ثانیه انصراف)"):
                    st.session_state.reset_requested = True
            
            with col2:
                if st.session_state.reset_requested:
                    if st.button("❌ انصراف و لغو عملیات"):
                        st.session_state.reset_requested = False
                        st.info("عملیات پاکسازی با موفقیت لغو شد.")
                        time.sleep(1)
                        st.rerun()

            if st.session_state.reset_requested:
                progress_bar = st.progress(100)
                status_text = st.empty()
                
                for i in range(5, 0, -1):
                    if not st.session_state.reset_requested:
                        break
                    status_text.warning(f"⚠️ پاکسازی دیتابیس تا {i} ثانیه دیگر انجام می‌شود... در صورت پشیمانی دکمه انصراف را بزنید!")
                    progress_bar.progress(i * 20)
                    time.sleep(1)
                    
                if st.session_state.reset_requested:
                    status_text.empty()
                    progress_bar.empty()
                    if reset_club_data(club_id):
                        st.session_state.reset_requested = False
                        st.success("🎉 تمامی داده‌های این باشگاه با موفقیت پاک شدند.")
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error("خطا در ریست دیتابیس.")