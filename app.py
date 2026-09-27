import streamlit as st
import pandas as pd
import time
from db_manager import (
    add_member, 
    get_all_members, 
    search_member, 
    delete_member, 
    record_attendance, 
    add_package,
    get_all_packages,
    assign_package_to_member
)
from ai_analytics import get_hourly_occupancy, predict_churn_risk
from auth import authenticate_user, add_user

st.set_page_config(page_title="سامانه مدیریت هوشمند باشگاه آنلاین", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] {
        direction: rtl;
        text-align: right;
        font-family: 'Tahoma', 'Vazirmatn', sans-serif;
    }
    div[data-baseweb="select"] {
        direction: rtl !important;
        text-align: right !important;
    }
    </style>
""", unsafe_allow_html=True)

# مدیریت نشست کاربر
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'club_id' not in st.session_state:
    st.session_state.club_id = ""

query_params = st.query_params
if not st.session_state.logged_in and "user" in query_params:
    st.session_state.logged_in = True
    st.session_state.username = query_params["user"]
    st.session_state.club_id = query_params.get("club", query_params["user"])

# --- ورود / ثبت‌نام آنلاین (دست‌نخورده) ---
if not st.session_state.logged_in:
    st.subheader("🔑 ورود یا ثبت‌نام باشگاه")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔐 ورود به سیستم", "👤 ثبت‌نام مدیر/باشگاه جدید"])
        
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
                            st.query_params["user"] = username_input
                            st.query_params["club"] = club_id
                            st.success(f"خوش آمدید {username_input}!")
                            time.sleep(1)
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
                            st.success("حساب با موفقیت ساخته شد.")
                        else:
                            st.error("خطا در ساخت حساب.")
                    else:
                        st.warning("لطفاً تمام فیلدها را پر کنید.")

# --- محتوای اصلی برنامه (تطبیق‌یافته با لوکال) ---
else:
    st.sidebar.write(f"👤 **مدیر:** {st.session_state.username}")
    st.sidebar.write(f"🏢 **شناسه باشگاه:** `{st.session_state.club_id}`")
    
    if st.sidebar.button("🚪 خروج"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.club_id = ""
        st.query_params.clear()
        st.rerun()

    st.sidebar.markdown("---")
    
    menu = [
        "📋 لیست اعضا", 
        "➕ ثبت عضو جدید", 
        "📦 تعریف و تخصیص بسته", 
        "🚪 ثبت تردد (Check-in)", 
        "📊 تحلیل هوش مصنوعی", 
        "🗑️ مدیریت و حذف"
    ]

    choice = st.sidebar.selectbox("منوی اصلی", menu)
    club_id = st.session_state.club_id

    # ۱. لیست اعضا
    if choice == "📋 لیست اعضا":
        st.subheader("📋 لیست تمامی اعضای ثبت‌شده")
        search_query = st.text_input("🔍 جستجوی عضو (نام یا کد ملی):")
        members = search_member(search_query, club_id) if search_query.strip() else get_all_members(club_id)
        
        if members:
            df = pd.DataFrame(members)
            df_display = df.rename(columns={
                'id': 'شناسه',
                'name': 'نام و نام خانوادگی',
                'phone': 'شماره تماس',
                'national_id': 'کد ملی',
                'join_date': 'تاریخ عضویت',
                'subscription_days': 'روزهای اعتبار',
                'sessions_left': 'جلسات باقی‌مانده',
                'status': 'وضعیت'
            })
            if 'club_id' in df_display.columns:
                df_display = df_display.drop(columns=['club_id'])
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("هیچ عضوی یافت نشد.")

    # ۲. ثبت عضو جدید
    elif choice == "➕ ثبت عضو جدید":
        st.subheader("➕ ثبت عضو جدید در باشگاه")
        with st.form("add_member_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("نام و نام خانوادگی")
                phone = st.text_input("شماره تماس")
            with col2:
                national_id = st.text_input("کد ملی")
                subscription_days = st.number_input("روزهای اعتبار اولیه", min_value=0, value=30)
                sessions_left = st.number_input("تعداد جلسات اولیه", min_value=0, value=12)
                
            submit = st.form_submit_button("ثبت عضو", type="primary")
            if submit:
                if name.strip() and phone.strip() and national_id.strip():
                    if add_member(name, phone, national_id, subscription_days, sessions_left, club_id):
                        st.success("عضو جدید با موفقیت ثبت شد.")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("لطفاً تمامی فیلدها را وارد کنید.")

    # ۳. تعریف و تخصیص بسته (مطابق لوکال)
    elif choice == "📦 تعریف و تخصیص بسته":
        tab1, tab2 = st.tabs(["➕ تعریف بسته جدید", "💳 تخصیص بسته به عضو"])
        
        with tab1:
            with st.form("add_package_form", clear_on_submit=True):
                pkg_title = st.text_input("عنوان بسته (مثلا: ۱۲ جلسه ماهانه)")
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    pkg_sessions = st.number_input("تعداد جلسات", min_value=1, value=12)
                with col_b:
                    pkg_days = st.number_input("مدت اعتبار (روز)", min_value=1, value=30)
                with col_c:
                    pkg_price = st.number_input("قیمت (تومان)", min_value=0, value=500000)
                
                submit_pkg = st.form_submit_button("ایجاد بسته", type="primary")
                if submit_pkg:
                    if pkg_title.strip():
                        if add_package(pkg_title, pkg_sessions, pkg_days, pkg_price, club_id):
                            st.success("بسته جدید با موفقیت اضافه شد.")
                    else:
                        st.warning("عنوان بسته را وارد کنید.")
                        
        with tab2:
            members = get_all_members(club_id)
            packages = get_all_packages(club_id)
            
            if members and packages:
                m_options = {f"👤 {m['name']} (جلسات: {m.get('sessions_left', 0)} | روزها: {m.get('subscription_days', 0)})": m['id'] for m in members}
                p_options = {f"📦 {p['title']} ({p['sessions']} جلسه - {p['duration_days']} روز)": p['id'] for p in packages}
                
                selected_member = st.selectbox("انتخاب عضو:", list(m_options.keys()))
                selected_package = st.selectbox("انتخاب بسته:", list(p_options.keys()))
                
                if st.button("🔄 تخصیص بسته و تمدید", type="primary"):
                    m_id = m_options[selected_member]
                    p_id = p_options[selected_package]
                    if assign_package_to_member(m_id, p_id, club_id):
                        st.success("بسته با موفقیت به حساب عضو اضافه شد.")
                        time.sleep(1)
                        st.rerun()
            else:
                st.info("ابتدا باید حداقل یک عضو و یک بسته ثبت شده باشد.")

    # ۴. ثبت تردد
    elif choice == "🚪 ثبت تردد (Check-in)":
        st.subheader("🚪 ثبت ورود و کسر جلسه")
        members = get_all_members(club_id)
        if members:
            m_options = {f"👤 {m['name']} | جلسات باقی‌مانده: {m.get('sessions_left', 0)}": m['id'] for m in members}
            selected_m = st.selectbox("انتخاب عضو جهت ورود:", list(m_options.keys()))
            
            if st.button("🟢 ثبت ورود", type="primary"):
                m_id = m_options[selected_m]
                success, msg = record_attendance(m_id, club_id)
                if success:
                    st.success(msg)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.info("هیچ عضوی یافت نشد.")

    # ۵. تحلیل هوش مصنوعی
    elif choice == "📊 تحلیل هوش مصنوعی":
        st.subheader("🤖 هوش مصنوعی: تحلیل رفتار و پیش‌بینی ریزش اعضا")
        
        hourly_df = get_hourly_occupancy(club_id)
        churn_df = predict_churn_risk(club_id)
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("### 📈 نمودار ساعات شلوغی باشگاه")
            if not hourly_df.empty:
                st.bar_chart(data=hourly_df, x='hour', y='checkin_count', color="#1f77b4")
            else:
                st.info("داده ترددی ثبت نشده است.")
                
        with col2:
            st.write("### ⚠️ تحلیل و محاسبه امتیاز Churn Risk")
            if not churn_df.empty:
                display_churn = churn_df.rename(columns={
                    'name': 'نام',
                    'phone': 'شماره',
                    'days_absent': 'روزهای غیبت',
                    'sessions_left': 'جلسات مانده',
                    'churn_score': 'امتیاز ریزش (۰-۱۰۰)',
                    'risk_level': 'سطح ریسک'
                })
                st.dataframe(display_churn[['نام', 'شماره', 'روزهای غیبت', 'امتیاز ریزش (۰-۱۰۰)', 'سطح ریسک']], use_container_width=True, hide_index=True)

    # ۶. مدیریت و حذف
    elif choice == "🗑️ مدیریت و حذف":
        st.subheader("🗑️ حذف کامل عضو")
        members = get_all_members(club_id)
        if members:
            m_options = {f"کد: {m['id']} | {m['name']}": m['id'] for m in members}
            selected_del = st.selectbox("انتخاب جهت حذف:", list(m_options.keys()))
            
            if st.button("❌ حذف قطعی"):
                if delete_member(m_options[selected_del], club_id):
                    st.success("عضو با موفقیت حذف شد.")
                    time.sleep(1)
                    st.rerun()