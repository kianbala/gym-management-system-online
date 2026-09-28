import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time

from db_manager import (
    add_member, 
    get_all_members, 
    search_member, 
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

st.set_page_config(page_title="سامانه مدیریت هوشمند باشگاه (Supabase)", layout="wide")

# -------------------------------------------------------------
# استایل‌دهی سفارشی (راست‌چین‌سازی کامل)
# -------------------------------------------------------------
st.markdown("""
    <style>
    html, body, [class*="css"] {
        direction: rtl;
        text-align: right !important;
        font-family: 'Tahoma', 'Vazirmatn', sans-serif;
    }
    
    div[data-testid="stMarkdownContainer"], 
    div[data-testid="stMarkdownContainer"] > *,
    .stMarkdown, h1, h2, h3, h4, h5, h6, p, label {
        text-align: right !important;
        direction: rtl !important;
    }

    div[data-baseweb="select"] {
        direction: rtl !important;
        text-align: right !important;
    }
    div[data-testid="InputInstructions"] {
        display: none !important;
    }
    .stDataFrame {
        direction: rtl !important;
    }

    section[data-testid="stSidebar"] {
        overflow: hidden !important;
    }
    section[data-testid="stSidebar"][aria-expanded="false"] {
        visibility: hidden !important;
    }
    section[data-testid="stSidebar"][aria-expanded="false"] * {
        display: none !important;
    }
    div[data-testid="stSidebarCollapsedControl"] {
        visibility: visible !important;
        display: block !important;
        z-index: 999999 !important;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        white-space: nowrap !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
        color: #b0b8c5 !important;
        white-space: nowrap !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.72rem !important;
    }

    div[data-testid="metric-container"] {
        background-color: #1a1f2c;
        border: 1px solid #2e3545;
        padding: 8px 12px;
        border-radius: 8px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
    }

    h1, h2, h3 {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        margin-bottom: 0.5rem !important;
    }
    .stSubheader {
        font-size: 1.05rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# مدیریت نشست کاربر (Session State)
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

# -------------------------------------------------------------
# ۱. صفحه ورود و ثبت‌نام
# -------------------------------------------------------------
if not st.session_state.logged_in:
    st.markdown("<h3 style='text-align: right;'>🔑 ورود یا ثبت‌نام باشگاه</h3>", unsafe_allow_html=True)
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
                            st.success(f"باشگاه '{reg_club_name}' با مدیریت '{reg_username}' ایجاد شد! اکنون می‌توانید وارد شوید.")
                        else:
                            st.error("خطا در ساخت حساب (نام کاربری تکراری است).")
                    else:
                        st.warning("لطفاً تمامی فیلدها را پر کنید.")

# -------------------------------------------------------------
# ۲. پنل اصلی باشگاه (پس از ورود)
# -------------------------------------------------------------
else:
    st.sidebar.write(f"👤 **مدیر آنلاین:** {st.session_state.username}")
    st.sidebar.markdown(
        f"🏢 **باشگاه:** <span style='color: #00e676; font-size: 1.2rem; font-weight: bold;'>{st.session_state.club_id}</span>",
        unsafe_allow_html=True
    )
    
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
        "ثبت تردد", 
        "تخصیص بسته", 
        "📊 تحلیل و هوش مصنوعی", 
        "مدیریت و حذف",
        "⚙️ ساخت باشگاه/مدیر جدید"
    ]

    choice = st.sidebar.selectbox("منوی اصلی", menu)
    club_id = st.session_state.club_id

    # ---------------------------------------------------------
    # بخش ۱: داشبورد و لیست اعضا
    # ---------------------------------------------------------
    if choice == "داشبورد و اعضا":
        st.markdown("<h3 style='text-align: right; margin-bottom: 1rem;'>📑 لیست اعضا و وضعیت اشتراک‌ها</h3>", unsafe_allow_html=True)
        
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
                if sub_days > 12:
                    package_type = "بسته ۲ | یک ماه ۲۴ جلسه | 1,400,000 تومان"
                else:
                    package_type = "بسته ۱ | یک ماه ۱۲ جلسه | 800,000 تومان"

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

                sub_code = str(m_id)
                sessions_left = sub_days
                status_str = "EXPIRED" if is_expired_by_time else "ACTIVE"
            else:
                package_type = "-"
                sub_code = "-"
                sessions_left = "-"
                expire_str = "-"
                status_str = "فاقد اشتراک"

            if m_id in last_checkin_map:
                days_absent = (now_date - last_checkin_map[m_id]).days
            elif join_date_str:
                try:
                    clean_join = join_date_str.split('T')[0]
                    join_dt = datetime.strptime(clean_join, "%Y-%m-%d").date()
                    days_absent = (now_date - join_dt).days
                except Exception:
                    days_absent = 0
            else:
                days_absent = 0

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
                "روزهای غیبت": max(0, days_absent)
            })

        col_filter, col_search = st.columns([1, 2])
        
        with col_filter:
            status_filter = st.selectbox(
                "فیلتر وضعیت اشتراک:",
                ["همه", "ACTIVE", "EXPIRED", "فاقد اشتراک"]
            )

        with col_search:
            search_query = st.text_input(
                "🔍 جستجوی عضو (نام، شماره، کد ملی یا کد عضویت):",
                placeholder="مثلاً: علی، 0912 یا کد عضویت..."
            )

        filtered_list = processed_data
        if status_filter != "همه":
            filtered_list = [item for item in filtered_list if item["وضعیت"] == status_filter]

        if search_query.strip():
            q = search_query.strip().lower()
            filtered_list = [
                item for item in filtered_list
                if q in str(item["نام و نام خانوادگی"]).lower()
                or q in str(item["کد ملی"])
                or q in str(item["شماره تماس"])
                or q in str(item["کد عضویت"])
            ]

        st.markdown(
            f"<div style='text-align: right; font-weight: bold; margin-top: 10px; margin-bottom: 10px;'>📊 تعداد اعضای یافت شده: {len(filtered_list)} نفر</div>",
            unsafe_allow_html=True
        )

        if filtered_list:
            df = pd.DataFrame(filtered_list)
            column_order = [
                "کد عضویت", "نام و نام خانوادگی", "کد ملی", "شماره تماس",
                "نوع بسته", "کد اشتراک", "جلسات باقی‌مانده", "تاریخ انقضا",
                "وضعیت", "روزهای غیبت"
            ]
            df = df[column_order]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("هیچ عضوی با مشخصات وارد شده یافت نشد.")

    # ---------------------------------------------------------
    # بخش ۲: ثبت عضو جدید (اصلاح‌شده با تاریخ سیستمی)
    # ---------------------------------------------------------
    elif choice == "ثبت عضو جدید":
        st.markdown("<h3 style='text-align: right;'>➕ ثبت عضو جدید</h3>", unsafe_allow_html=True)
        with st.form("add_member_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                first_name = st.text_input("نام")
                last_name = st.text_input("نام خانوادگی")
            with col2:
                national_id = st.text_input("کد ملی (۱۰ رقمی)")
                phone = st.text_input("شماره تماس (۱۱ رقمی)")
                
            submit = st.form_submit_button("ثبت عضو", type="primary")
            
            if submit:
                f_name = first_name.strip()
                l_name = last_name.strip()
                n_id = national_id.strip()
                ph = phone.strip()
                
                if not (f_name and l_name and n_id and ph):
                    st.warning("لطفاً تمامی فیلدها را پر کنید.")
                elif not (n_id.isdigit() and len(n_id) == 10):
                    st.error("❌ کد ملی باید دقیقاً ۱۰ رقم عددی باشد.")
                elif not (ph.isdigit() and len(ph) == 11):
                    st.error("❌ شماره تماس باید دقیقاً ۱۱ رقم عددی باشد.")
                else:
                    full_name = f"{f_name} {l_name}"
                    # ثبت تاریخ عضویت بر اساس تاریخ جاری سیستم
                    success, message = add_member(full_name, ph, n_id, club_id, subscription_days=0)
                    if success:
                        st.success(message)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(message)

    # ---------------------------------------------------------
    # بخش ۳: ثبت تردد
    # ---------------------------------------------------------
    elif choice == "ثبت تردد":
        st.markdown("<h3 style='text-align: right;'>🚪 ثبت ورود ورزشکار و کسر جلسه</h3>", unsafe_allow_html=True)
        
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
        
        search_query = st.text_input(
            "🔍 جستجوی ورزشکار (نام، شماره تماس، کد ملی یا کد عضویت):",
            placeholder="مثلاً: علی، 0912 یا کد عضویت..."
        )
        
        filtered_members = active_members
        if search_query.strip():
            q = search_query.strip().lower()
            filtered_members = [
                m for m in active_members
                if q in str(m.get("name", "")).lower()
                or q in str(m.get("phone", ""))
                or q in str(m.get("national_id", ""))
                or q in str(m.get("id", ""))
            ]
            
        st.markdown(f"<div style='text-align: right;'>🔍 <b>تعداد {len(filtered_members)} مورد یافت شد:</b></div>", unsafe_allow_html=True)
        
        if filtered_members:
            options = {
                f"👤 {m.get('name', '')} | 📱 {m.get('phone', '')} | 🔢 باقیمانده: {m.get('subscription_days', 0)} جلسه (کد عضویت: {m.get('id')})": m.get('id')
                for m in filtered_members
            }
            
            selected_label = st.selectbox("لیست افراد یافت‌شده:", list(options.keys()))
            member_id = options[selected_label]
            
            if st.button("🟢 ثبت ورود", type="primary"):
                if record_attendance(member_id, club_id):
                    if decrement_subscription(member_id, club_id):
                        current_sub = next((m.get("subscription_days", 0) for m in filtered_members if m.get("id") == member_id), 1)
                        new_sub = max(0, current_sub - 1)
                        st.success(f"ورود با موفقیت ثبت شد. (جلسات باقیمانده: {new_sub})")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.success("ورود ثبت شد اما در کسر جلسه خطایی رخ داد.")
                else:
                    st.error("خطا در ثبت ورود.")
        else:
            st.info("هیچ ورزشکار فعالی با این مشخصات یافت نشد.")

    # ---------------------------------------------------------
    # بخش ۴: تخصیص بسته (فقط ۱۲ یا ۲۴ جلسه‌ای)
    # ---------------------------------------------------------
    elif choice == "تخصیص بسته":
        st.markdown("<h3 style='text-align: right;'>💳 اختصاص بسته جدید به عضو</h3>", unsafe_allow_html=True)
        
        raw_members = get_all_members(club_id)
        now_date = datetime.now().date()

        member_options = {}
        status_warning_map = {}

        for m in raw_members:
            m_id = m.get("id")
            name = m.get("name", "")
            national_id = m.get("national_id", "")
            phone = m.get("phone", "")
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

            if is_expired or sub_days <= 0:
                status_label = "🟢 مجاز به تخصیص/تمدید (بدون بسته یا انقضا)"
                status_warning_map[m_id] = None
            else:
                status_label = f"🔴 دارای اشتراک فعال ({sub_days} جلسه باقی‌مانده)"
                status_warning_map[m_id] = f"🔴 دارای اشتراک فعال ({sub_days} جلسه باقی‌مانده). تا زمانی که جلسات به اتمام نرسد یا ۳۰ روز منقضی نشود، امکان ثبت بسته جدید نیست."

            label = f"👤 {name} | 📱 {phone} | 🆔 کد ملی: {national_id} | {status_label}"
            member_options[label] = m_id

        search_query = st.text_input(
            "🔍 جستجوی ورزشکار (نام، شماره تماس، کد ملی یا کد عضویت):",
            placeholder="مثلاً: حسین، 0912..."
        )

        filtered_labels = list(member_options.keys())
        if search_query.strip():
            q = search_query.strip().lower()
            filtered_labels = [lbl for lbl in filtered_labels if q in lbl.lower()]

        st.markdown(f"<div style='text-align: right;'>🔍 <b>تعداد {len(filtered_labels)} مورد یافت شد:</b></div>", unsafe_allow_html=True)

        if filtered_labels:
            selected_label = st.selectbox("انتخاب عضو:", filtered_labels)
            selected_member_id = member_options[selected_label]

            warning_msg = status_warning_map.get(selected_member_id)
            if warning_msg:
                st.warning(warning_msg)

            # محدودسازی دقیق بسته‌ها به ۱۲ و ۲۴ جلسه
            packages = {
                "بسته ۱ | یک ماه ۱۲ جلسه | 800,000 تومان": 12,
                "بسته ۲ | یک ماه ۲۴ جلسه | 1,400,000 تومان": 24
            }

            selected_package_label = st.selectbox("انتخاب بسته ورزشی:", list(packages.keys()))
            sessions_to_add = packages[selected_package_label]

            can_renew = warning_msg is None
            if st.button("💳 ثبت و اختصاص بسته", type="primary", disabled=not can_renew):
                # به‌روزرسانی تعداد جلسات همراه با بازنشانی تاریخ شروع به تاریخ امروز
                if update_subscription(selected_member_id, sessions_to_add, club_id, overwrite=True):
                    st.success(f"بسته جدید ({sessions_to_add} جلسه) از تاریخ امروز برای ورزشکار فعال شد (انقضا: ۳۰ روز آینده).")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("خطا در اختصاص بسته.")
        else:
            st.info("هیچ عضوی با مشخصات وارد شده یافت نشد.")

    # ---------------------------------------------------------
    # بخش ۵: تحلیل و هوش مصنوعی
    # ---------------------------------------------------------
    elif choice in ["📊 تحلیل و هوش مصنوعی", "📊 تحلیل هوش مصنوعی"]:
        st.markdown("<h3 style='text-align: right;'>🤖 ماژول تحلیلی و پیش‌بینی هوشمند (مخصوص اعضای فعال)</h3>", unsafe_allow_html=True)
        
        hourly_df = get_hourly_occupancy(club_id)
        churn_df = predict_churn_risk(club_id)
        raw_members = get_all_members(club_id)
        attendance_logs = get_attendance_logs(club_id)
        
        now_date = datetime.now().date()
        
        active_members_ids = set()
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
                active_members_ids.add(m.get("id"))

        active_count = len(active_members_ids)
        
        active_attendance_count = sum(
            1 for log in attendance_logs 
            if log.get('member_id') in active_members_ids
        )
        
        active_churn_df = pd.DataFrame()
        if not churn_df.empty:
            id_col = 'id' if 'id' in churn_df.columns else ('member_id' if 'member_id' in churn_df.columns else None)
            if id_col:
                active_churn_df = churn_df[churn_df[id_col].isin(active_members_ids)].copy()
            else:
                active_churn_df = churn_df.copy()

        if not hourly_df.empty and 'checkin_count' in hourly_df.columns:
            peak_row = hourly_df.loc[hourly_df['checkin_count'].idxmax()]
            peak_hour_str = f"ساعت {int(peak_row['hour']):02d}:00"
        else:
            peak_hour_str = "نامشخص"

        high_risk_cnt = 0
        med_risk_cnt = 0
        low_risk_cnt = 0

        if active_count > 0:
            if not active_churn_df.empty:
                for _, row in active_churn_df.iterrows():
                    score = float(row.get('churn_risk_score', 0))
                    r_level = str(row.get('risk_level', '')).lower()
                    
                    if 'high' in r_level or 'بالا' in r_level or score >= 70:
                        high_risk_cnt += 1
                    elif 'med' in r_level or 'متوسط' in r_level or score >= 40:
                        med_risk_cnt += 1
                    else:
                        low_risk_cnt += 1

                low_risk_cnt = max(0, active_count - high_risk_cnt - med_risk_cnt)
            else:
                low_risk_cnt = active_count

        high_pct = (high_risk_cnt / active_count) * 100 if active_count > 0 else 0
        med_pct = (med_risk_cnt / active_count) * 100 if active_count > 0 else 0
        low_pct = (low_risk_cnt / active_count) * 100 if active_count > 0 else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("مجموع ترددهای اعضای فعال", f"{active_attendance_count} ورود")
        with c2:
            st.metric("شلوغ‌ترین زمان", peak_hour_str)
        with c3:
            st.metric("🔴 ریسک بالا", f"{high_risk_cnt} نفر", f"↑ {high_pct:.1f}%")
        with c4:
            st.metric("🟡 ریسک متوسط", f"{med_risk_cnt} نفر", f"↑ {med_pct:.1f}%")
        with c5:
            st.metric("🟢 ریسک پایین", f"{low_risk_cnt} نفر", f"↑ {low_pct:.1f}%")

        st.markdown("<br>", unsafe_allow_html=True)

        col_chart, col_table = st.columns([1, 1])

        with col_chart:
            st.markdown("<h3 style='text-align: right;'>📈 تحلیل ساعات شلوغی باشگاه</h3>", unsafe_allow_html=True)
            if not hourly_df.empty:
                st.bar_chart(data=hourly_df, x='hour', y='checkin_count', color="#1f77b4")
                st.caption("پراکندگی ورود ورزشکاران در طول ۲۴ ساعت شبانه‌روز")
            else:
                st.info("هنوز ترددی ثبت نشده است.")

        with col_table:
            st.markdown("<h3 style='text-align: right;'>⚠️ پیش‌بینی ریسک ریزش اعضای فعال (AI Engine)</h3>", unsafe_allow_html=True)
            
            table_rows = []
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not active_churn_df.empty:
                for _, row in active_churn_df.iterrows():
                    m_id = row.get('id', row.get('member_id', '-'))
                    name = row.get('name', '-')
                    phone = row.get('phone', '-')
                    
                    score = int(row.get('churn_risk_score', 0))
                    r_level = str(row.get('risk_level', ''))
                    
                    if 'high' in r_level.lower() or 'بالا' in r_level or score >= 70:
                        level_str = "🔴 بالا (High)"
                    elif 'med' in r_level.lower() or 'متوسط' in r_level or score >= 40:
                        level_str = "🟡 متوسط (Medium)"
                    else:
                        level_str = "🟢 پایین (Low)"

                    table_rows.append({
                        "کد عضویت": m_id,
                        "نام ورزشکار": name,
                        "شماره تماس": phone,
                        "نمره ریسک (۰ تا ۱۰۰)": score,
                        "سطح ریسک": level_str,
                        "تاریخ آخرین محاسبه": now_str
                    })

                df_table = pd.DataFrame(table_rows)
                df_table = df_table.sort_values(by="نمره ریسک (۰ تا ۱۰۰)", ascending=False)
                st.dataframe(df_table, use_container_width=True, hide_index=True)
            else:
                st.info("هیچ عضو فعالی در لیست تحلیلی قرار ندارد.")

            st.caption("محاسبات ریسک و درصدها فقط بر اساس اعضای دارای اشتراک فعال انجام شده است.")

    # ---------------------------------------------------------
    # بخش ۶: مدیریت و حذف
    # ---------------------------------------------------------
    elif choice == "مدیریت و حذف":
        raw_members = get_all_members(club_id)

        st.markdown("<h3 style='text-align: right;'>👤 حذف دستی یک عضو مشخص</h3>", unsafe_allow_html=True)
        search_del = st.text_input(
            "🔍 جستجوی عضو جهت حذف (بر اساس نام، شماره تماس یا کد ملی):",
            key="search_del_input"
        )

        filtered_del_members = raw_members
        if search_del.strip():
            q = search_del.strip().lower()
            filtered_del_members = [
                m for m in raw_members
                if q in str(m.get("name", "")).lower()
                or q in str(m.get("phone", ""))
                or q in str(m.get("national_id", ""))
                or q in str(m.get("id", ""))
            ]

        if filtered_del_members:
            del_options = {
                f"کد: {m.get('id')} | {m.get('name')} | همراه: {m.get('phone')} | کد ملی: {m.get('national_id', 'نامشخص')}": m.get('id')
                for m in filtered_del_members
            }
            selected_del_label = st.selectbox("عضو مورد نظر را برای حذف انتخاب کنید:", list(del_options.keys()))
            selected_del_id = del_options[selected_del_label]

            if st.button("❌ حذف کامل عضو", type="primary"):
                if delete_member(selected_del_id, club_id):
                    st.success("عضو مورد نظر با موفقیت حذف شد.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("خطا در حذف عضو.")
        else:
            st.info("هیچ عضوی یافت نشد.")

        st.markdown("---")

        st.markdown("<h3 style='text-align: right;'>🗑️ حذف اشتراک‌های اضافی (بدون حذف عضو)</h3>", unsafe_allow_html=True)
        search_sub = st.text_input(
            "🔍 جستجوی عضو جهت مدیریت/حذف اشتراک (نام، شماره تماس یا کد ملی):",
            key="search_sub_input"
        )

        filtered_sub_members = raw_members
        if search_sub.strip():
            q = search_sub.strip().lower()
            filtered_sub_members = [
                m for m in raw_members
                if q in str(m.get("name", "")).lower()
                or q in str(m.get("phone", ""))
                or q in str(m.get("national_id", ""))
                or q in str(m.get("id", ""))
            ]

        if filtered_sub_members:
            sub_member_options = {
                f"کد: {m.get('id')} | {m.get('name')} | همراه: {m.get('phone')}": m
                for m in filtered_sub_members
            }
            selected_sub_label = st.selectbox("عضو مورد نظر را انتخاب کنید:", list(sub_member_options.keys()))
            selected_sub_member = sub_member_options[selected_sub_label]
            m_id = selected_sub_member.get('id')
            sub_days = selected_sub_member.get('subscription_days', 0) or 0

            if sub_days > 0:
                package_desc = f"کد اشتراک: {m_id} | پکیج: {sub_days} جلسه باقیمانده"
                st.selectbox("اشتراکی که قصد حذف آن را دارید انتخاب کنید:", [package_desc])

                if st.button("❌ حذف این اشتراک"):
                    if clear_member_subscription(m_id, club_id):
                        st.success("اشتراک عضو با موفقیت صفر گردید.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("خطا در صفر کردن اشتراک.")
            else:
                st.info("این عضو در حال حاضر اشتراک فعالی ندارد.")
        else:
            st.info("عضوی یافت نشد.")

        st.markdown("---")

        st.markdown("<h3 style='text-align: right;'>⚠️ ریست کامل دیتابیس (حذف تمامی اعضا و داده‌ها)</h3>", unsafe_allow_html=True)
        st.error("🚨 هشدار: این عملیات غیرقابل بازگشت است و تمام اعضا، اشتراک‌ها و ترددهای این باشگاه را کاملاً حذف می‌کند!")

        confirm_text = st.text_input("برای تایید، عبارت 'RESET' را به انگلیسی وارد کنید:")

        if 'reset_pending' not in st.session_state:
            st.session_state.reset_pending = False

        col_btn1, col_btn2 = st.columns([1, 1])

        with col_btn1:
            if st.button("💥 ریست کلی دیتابیس باشگاه", type="primary"):
                if confirm_text.strip() == "RESET":
                    st.session_state.reset_pending = True
                    st.session_state.reset_start_time = time.time()
                    st.rerun()
                else:
                    st.warning("جهت تایید نهایی لطفاً کلمه RESET را به درستی وارد کنید.")

        with col_btn2:
            if st.session_state.reset_pending:
                if st.button("🛑 لغو عملیات ریست", type="secondary"):
                    st.session_state.reset_pending = False
                    st.session_state.pop('reset_start_time', None)
                    st.info("عملیات ریست دیتابیس لغو شد.")
                    time.sleep(1)
                    st.rerun()

        if st.session_state.reset_pending:
            elapsed = time.time() - st.session_state.get('reset_start_time', time.time())
            remaining = 3 - int(elapsed)

            if remaining > 0:
                st.warning(f"⏳ پاکسازی کامل دیتابیس تا {remaining} ثانیه دیگر... (برای انصراف روی دکمه «لغو عملیات» کلیک کنید)")
                time.sleep(0.5)
                st.rerun()
            else:
                if reset_club_data(club_id):
                    st.session_state.reset_pending = False
                    st.session_state.pop('reset_start_time', None)
                    st.success("تمامی داده‌ها و اعضای این باشگاه با موفقیت حذف و ریست گردید.")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.session_state.reset_pending = False
                    st.session_state.pop('reset_start_time', None)
                    st.error("خطا در ریست کامل دیتابیس.")

    # ---------------------------------------------------------
    # بخش ۷: ایجاد حساب جدید
    # ---------------------------------------------------------
    elif choice == "⚙️ ساخت باشگاه/مدیر جدید":
        st.markdown("<h3 style='text-align: right;'>👤 ساخت حساب باشگاه جدید</h3>", unsafe_allow_html=True)
        with st.form("new_user_form", clear_on_submit=True):
            new_username = st.text_input("نام کاربری جدید مدیر")
            new_club_name = st.text_input("نام جدید باشگاه / شرکت")
            new_password = st.text_input("رمز عبور جدید", type="password")
            submit_user = st.form_submit_button("ایجاد حساب باشگاه")
            
            if submit_user:
                if new_username.strip() and new_password.strip() and new_club_name.strip():
                    if add_user(new_username, new_password, club_name=new_club_name):
                        st.success(f"حساب باشگاه ({new_club_name}) برای مدیر ({new_username}) ساخته شد.")
                    else:
                        st.error("خطا در ساخت حساب.")
                else:
                    st.warning("لطفاً تمامی فیلدها را پر کنید.")