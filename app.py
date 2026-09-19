import streamlit as st
import pandas as pd
import time
from db_manager import (
    add_member, 
    get_all_members, 
    search_member, 
    update_subscription, 
    delete_member, 
    record_attendance, 
    get_attendance_logs
)
from ai_analytics import get_hourly_occupancy, predict_churn_risk
from auth import authenticate_user, add_user

st.set_page_config(page_title="سامانه مدیریت هوشمند باشگاه (Supabase)", layout="wide")

# استایل RTL
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
    div[data-testid="InputInstructions"] {
        display: none !important;
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

# --- فرم ورود و ثبت‌نام اولیه ---
if not st.session_state.logged_in:
    st.subheader("🔑 ورود یا ثبت‌نام باشگاه")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔐 ورود به سیستم", "👤 ثبت‌نام مدیر/باشگاه جدید"])
        
        # تب ورود
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
                            st.success(f"خوش آمدید {username_input}!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("نام کاربری یا رمز عبور اشتباه است.")
                    else:
                        st.warning("لطفاً اطلاعات را کامل وارد کنید.")
                        
        # تب ثبت‌نام
        with tab_register:
            with st.form("register_form"):
                reg_username = st.text_input("نام کاربری مدیر / نام باشگاه")
                reg_password = st.text_input("رمز عبور", type="password")
                submit_reg = st.form_submit_button("ساخت حساب باشگاه جدید", type="primary")
                
                if submit_reg:
                    if reg_username.strip() and reg_password.strip():
                        if add_user(reg_username, reg_password):
                            st.success("حساب باشگاه با موفقیت ساخته شد! اکنون می‌توانید وارد شوید.")
                        else:
                            st.error("خطا در ساخت حساب (احتمالاً این نام کاربری قبلاً ثبت شده است).")
                    else:
                        st.warning("لطفاً تمام فیلدها را پر کنید.")

# --- محتوای اصلی ---
else:
    st.sidebar.write(f"👤 **مدیر آنلاین:** {st.session_state.username}")
    st.sidebar.write(f"🏢 **باشگاه:** `{st.session_state.club_id}`")
    if st.sidebar.button("🚪 خروج"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.club_id = ""
        st.rerun()

    st.sidebar.markdown("---")
    
    menu = [
        "داشبورد و اعضا", 
        "ثبت عضو جدید", 
        "ثبت تردد", 
        "تمدید اشتراک", 
        "📊 تحلیل هوش مصنوعی", 
        "مدیریت و حذف",
        "⚙️ ساخت باشگاه/مدیر جدید"
    ]

    choice = st.sidebar.selectbox("منوی اصلی", menu)
    club_id = st.session_state.club_id

    # ۱. مشاهده اعضا
    if choice == "داشبورد و اعضا":
        st.subheader(f"📋 لیست اعضای ثبت‌شده در باشگاه {st.session_state.username}")
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
                'status': 'وضعیت'
            })
            if 'club_id' in df_display.columns:
                df_display = df_display.drop(columns=['club_id'])
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("هیچ عضوی برای این باشگاه یافت نشد.")

    # ۲. ثبت عضو جدید
    elif choice == "ثبت عضو جدید":
        st.subheader("➕ ثبت عضو جدید")
        with st.form("add_member_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("نام و نام خانوادگی")
                phone = st.text_input("شماره تماس")
            with col2:
                national_id = st.text_input("کد ملی")
                subscription_days = st.number_input("تعداد روزهای اعتبار اولیه", min_value=1, value=30)
                
            submit = st.form_submit_button("ثبت در دیتابیس", type="primary")
            if submit:
                if name.strip() and phone.strip() and national_id.strip():
                    if add_member(name, phone, national_id, subscription_days, club_id):
                        st.success("عضو جدید با موفقیت برای باشگاه شما ثبت شد.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("خطا در ثبت عضو.")
                else:
                    st.warning("لطفاً همه فیلدها را پر کنید.")

    # ۳. ثبت تردد
    elif choice == "ثبت تردد":
        st.subheader("🚪 ثبت ورود ورزشکار")
        members = get_all_members(club_id)
        if members:
            options = {f"👤 {m['name']} | 📱 {m['phone']} (اعتبار: {m['subscription_days']} روز)": m['id'] for m in members}
            selected_label = st.selectbox("انتخاب عضو:", list(options.keys()))
            member_id = options[selected_label]
            
            if st.button("🟢 ثبت ورود", type="primary"):
                if record_attendance(member_id, club_id):
                    st.success("ورود با موفقیت ثبت شد.")
                else:
                    st.error("خطا در ثبت ورود.")
        else:
            st.warning("هیچ عضوی برای این باشگاه یافت نشد.")

    # ۴. تمدید اشتراک
    elif choice == "تمدید اشتراک":
        st.subheader("💳 تمدید اعتبار اشتراک")
        members = get_all_members(club_id)
        if members:
            options = {f"👤 {m['name']} | اعتبار فعلی: {m['subscription_days']} روز": m['id'] for m in members}
            selected_label = st.selectbox("انتخاب عضو جهت تمدید:", list(options.keys()))
            member_id = options[selected_label]
            add_days = st.number_input("تعداد روزهای افزایشی", min_value=1, value=30)
            
            if st.button("🔄 افزایش اعتبار", type="primary"):
                if update_subscription(member_id, add_days, club_id):
                    st.success("اعتبار عضو با موفقیت به روز شد.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("خطا در به‌روزرسانی اعتبار.")

    # ۵. تحلیل هوش مصنوعی
    elif choice == "📊 تحلیل هوش مصنوعی":
        st.subheader("🤖 تحلیل رفتاری و شلوغی باشگاه")
        try:
            hourly_df = get_hourly_occupancy(club_id)
            churn_df = predict_churn_risk(club_id)
        except TypeError:
            hourly_df = get_hourly_occupancy()
            churn_df = predict_churn_risk()
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("### 📈 نمودار ساعات شلوغی")
            st.bar_chart(data=hourly_df, x='hour', y='checkin_count', color="#1f77b4")
        with col2:
            st.write("### ⚠️ تحلیل ریسک ریزش اعضا")
            if not churn_df.empty:
                display_churn = churn_df[['name', 'phone', 'days_since_last_checkin', 'risk_level']].rename(columns={
                    'name': 'نام',
                    'phone': 'شماره تماس',
                    'days_since_last_checkin': 'روزهای غیبت',
                    'risk_level': 'سطح ریسک'
                })
                st.dataframe(display_churn, use_container_width=True, hide_index=True)

    # ۶. مدیریت و حذف
    elif choice == "مدیریت و حذف":
        st.subheader("🗑️ حذف کامل عضو")
        members = get_all_members(club_id)
        if members:
            options = {f"کد: {m['id']} | {m['name']}": m['id'] for m in members}
            selected_option = st.selectbox("عضو مورد نظر جهت حذف:", list(options.keys()))
            
            if st.button("❌ حذف عضو"):
                if delete_member(options[selected_option], club_id):
                    st.success("عضو با موفقیت حذف شد.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("خطا در حذف عضو.")

    # ۷. تعریف کاربر/باشگاه جدید
    elif choice == "⚙️ ساخت باشگاه/مدیر جدید":
        st.subheader("👤 ساخت حساب باشگاه جدید")
        with st.form("new_user_form", clear_on_submit=True):
            new_username = st.text_input("نام کاربری جدید (نام باشگاه)")
            new_password = st.text_input("رمز عبور جدید", type="password")
            submit_user = st.form_submit_button("ایجاد حساب باشگاه")
            
            if submit_user:
                if new_username.strip() and new_password.strip():
                    if add_user(new_username, new_password):
                        st.success(f"حساب باشگاه جدید ({new_username}) با موفقیت ایجاد شد.")
                    else:
                        st.error("خطا در ساخت حساب.")
