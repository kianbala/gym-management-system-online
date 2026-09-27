import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time

from db_manager import (
    add_member, 
    get_all_members, 
    search_member, 
    update_subscription, 
    delete_member, 
    record_attendance,
    get_attendance_logs,
    supabase
)
from ai_analytics import get_hourly_occupancy, predict_churn_risk
from auth import authenticate_user, add_user

st.set_page_config(page_title="سامانه مدیریت هوشمند باشگاه (Supabase)", layout="wide")

# استایل‌دهی سفارشی راست‌به‌چپ
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
    .stDataFrame {
        direction: rtl !important;
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
        "ثبت تردد", 
        "تخصیص بسته", 
        "📊 تحلیل هوش مصنوعی", 
        "مدیریت و حذف",
        "⚙️ ساخت باشگاه/مدیر جدید"
    ]

    choice = st.sidebar.selectbox("منوی اصلی", menu)
    club_id = st.session_state.club_id

    # ---------------------------------------------------------
    # بخش ۱: داشبورد و لیست اعضا و وضعیت اشتراک‌ها
    # ---------------------------------------------------------
    if choice == "داشبورد و اعضا":
        st.subheader("📑 لیست اعضا و وضعیت اشتراک‌ها")
        
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
            is_expired_by_time = False
            
            # انقضای زمانی: دقیقا ۳۰ روز بعد از تاریخ ثبت‌نام/تمدید
            if join_date_str:
                try:
                    join_dt = datetime.strptime(join_date_str, "%Y-%m-%d").date()
                    expire_dt = join_dt + timedelta(days=30)
                    expire_str = expire_dt.isoformat()
                    if now_date > expire_dt:
                        is_expired_by_time = True
                except Exception:
                    expire_str = "نامشخص"
            else:
                expire_str = "نامشخص"

            # روزهای غیبت
            if m_id in last_checkin_map:
                days_absent = (now_date - last_checkin_map[m_id]).days
            elif join_date_str:
                try:
                    join_dt = datetime.strptime(join_date_str, "%Y-%m-%d").date()
                    days_absent = (now_date - join_dt).days
                except Exception:
                    days_absent = 0
            else:
                days_absent = 0

            # تعیین نوع بسته
            if sub_days > 12:
                package_type = "بسته ۲ | یک ماه ۲۴ جلسه | 1,400,000 تومان"
            else:
                package_type = "بسته ۱ | یک ماه ۱۲ جلسه | 800,000 تومان"

            # وضعیت: اگر ۳۰ روز گذشته باشد یا جلسات ۰ شده باشد -> EXPIRED
            if is_expired_by_time or sub_days <= 0:
                status_str = "EXPIRED"
            else:
                status_str = "ACTIVE"

            processed_data.append({
                "کد عضویت": m_id,
                "نام و نام خانوادگی": name,
                "کد ملی": national_id,
                "شماره تماس": phone,
                "نوع بسته": package_type,
                "کد اشتراک": m_id,
                "جلسات باقی‌مانده": sub_days,
                "تاریخ انقضا": expire_str,
                "وضعیت": status_str,
                "روزهای غیبت": max(0, days_absent),
                "is_active_flag": (status_str == "ACTIVE") # پرچم کمکی
            })

        col_filter, col_search = st.columns([1, 2])
        
        with col_filter:
            status_filter = st.selectbox(
                "فیلتر وضعیت اشتراک:",
                ["همه", "ACTIVE", "EXPIRED"]
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

        st.write(f"📊 **تعداد اعضای یافت شده:** {len(filtered_list)} نفر")

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
    # بخش ۲: ثبت عضو جدید
    # ---------------------------------------------------------
    elif choice == "ثبت عضو جدید":
        st.subheader("➕ ثبت عضو جدید")
        with st.form("add_member_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col2:
                first_name = st.text_input("نام")
                last_name = st.text_input("نام خانوادگی")
            with col1:
                national_id = st.text_input("کد ملی (۱۰ رقمی)")
                phone = st.text_input("شماره تماس (۱۱ رقمی)")
                package_choice = st.selectbox(
                    "انتخاب نوع بسته ورزشی:",
                    ["بسته ۱ | یک ماه ۱۲ جلسه | 800,000 تومان", "بسته ۲ | یک ماه ۲۴ جلسه | 1,400,000 تومان"]
                )
                
            submit = st.form_submit_button("ثبت عضو", type="primary")
            
            if submit:
                f_name = first_name.strip()
                l_name = last_name.strip()
                n_id = national_id.strip()
                ph = phone.strip()
                
                sessions = 12 if "12" in package_choice else 24
                
                if not (f_name and l_name and n_id and ph):
                    st.warning("لطفاً تمامی فیلدها را پر کنید.")
                elif not (n_id.isdigit() and len(n_id) == 10):
                    st.error("❌ کد ملی باید دقیقاً ۱۰ رقم عددی باشد.")
                elif not (ph.isdigit() and len(ph) == 11):
                    st.error("❌ شماره تماس باید دقیقاً ۱۱ رقم عددی باشد.")
                else:
                    full_name = f"{f_name} {l_name}"
                    success, message = add_member(full_name, ph, n_id, club_id, subscription_days=sessions)
                    if success:
                        st.success(message)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(message)

    # ---------------------------------------------------------
    # بخش ۳: ثبت تردد و کسر جلسه
    # ---------------------------------------------------------
    elif choice == "ثبت تردد":
        st.subheader("🚪 ثبت ورود ورزشکار و کسر جلسه")
        
        raw_members = get_all_members(club_id)
        now_date = datetime.now().date()
        
        # شناسایی دقیق اعضایی که ۳۰ روزشان تمام نشده و جلسه باقی‌مانده دارند
        active_members = []
        for m in raw_members:
            sub_days = m.get("subscription_days", 0) or 0
            join_date_str = m.get("join_date")
            
            is_expired = False
            if join_date_str:
                try:
                    join_dt = datetime.strptime(join_date_str, "%Y-%m-%d").date()
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
            
        st.write(f"🔍 **تعداد {len(filtered_members)} مورد یافت شد:**")
        
        if filtered_members:
            options = {
                f"👤 {m.get('name', '')} | 📱 {m.get('phone', '')} | 🔢 باقیمانده: {m.get('subscription_days', 0)} جلسه (کد عضویت: {m.get('id')})": m.get('id')
                for m in filtered_members
            }
            
            selected_label = st.selectbox("لیست افراد یافت‌شده:", list(options.keys()))
            member_id = options[selected_label]
            
            if st.button("🟢 ثبت ورود", type="primary"):
                if record_attendance(member_id, club_id):
                    current_sub = next((m.get("subscription_days", 0) for m in filtered_members if m.get("id") == member_id), 0)
                    new_sub = max(0, current_sub - 1)
                    
                    try:
                        supabase.table("members").update({"subscription_days": new_sub}).eq("id", member_id).execute()
                        st.success(f"ورود با موفقیت ثبت شد. (جلسات باقیمانده: {new_sub})")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.success("ورود ثبت شد اما در کسر جلسه خطایی رخ داد.")
                else:
                    st.error("خطا در ثبت ورود.")
        else:
            st.info("هیچ ورزشکار فعالی با این مشخصات یافت نشد.")

    # ---------------------------------------------------------
    # بخش ۴: تخصیص بسته جدید به عضو
    # ---------------------------------------------------------
    elif choice == "تخصیص بسته":
        st.subheader("💳 اختصاص بسته جدید به عضو")
        
        raw_members = get_all_members(club_id)
        attendance_logs = get_attendance_logs(club_id)
        now_date = datetime.now().date()

        # محاسبه آخرین تاریخ حضور هر عضو
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
                    join_dt = datetime.strptime(join_date_str, "%Y-%m-%d").date()
                    if now_date > (join_dt + timedelta(days=30)):
                        is_expired = True
                except Exception:
                    pass

            if is_expired or sub_days <= 0:
                status_label = "🟢 مجاز به تمدید (اتمام جلسات یا انقضا)"
                status_warning_map[m_id] = None
            else:
                status_label = f"🔴 دارای اشتراک فعال ({sub_days} جلسه باقی‌مانده)"
                status_warning_map[m_id] = f"🔴 دارای اشتراک فعال ({sub_days} جلسه باقی‌مانده). تا زمانی که جلسات به اتمام نرسد یا انقضا نیاید امکان ثبت بسته جدید نیست."

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

        st.write(f"🔍 **تعداد {len(filtered_labels)} مورد یافت شد:**")

        if filtered_labels:
            selected_label = st.selectbox("انتخاب عضو:", filtered_labels)
            selected_member_id = member_options[selected_label]

            warning_msg = status_warning_map.get(selected_member_id)
            if warning_msg:
                st.warning(warning_msg)

            packages = {
                "بسته ۱ | یک ماه ۱۲ جلسه | 800,000 تومان": 12,
                "بسته ۲ | یک ماه ۲۴ جلسه | 1,400,000 تومان": 24
            }

            selected_package_label = st.selectbox("انتخاب بسته ورزشی:", list(packages.keys()))
            sessions_to_add = packages[selected_package_label]

            can_renew = warning_msg is None
            if st.button("💳 ثبت و اختصاص بسته", type="primary", disabled=not can_renew):
                try:
                    today_str = now_date.isoformat()
                    supabase.table("members").update({
                        "subscription_days": sessions_to_add,
                        "join_date": today_str,
                        "status": "active"
                    }).eq("id", selected_member_id).eq("club_id", club_id).execute()

                    st.success(f"بسته جدید ({sessions_to_add} جلسه) با موفقیت به ورزشکار اختصاص یافت.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"خطا در اختصاص بسته: {e}")
        else:
            st.info("هیچ عضوی با مشخصات وارد شده یافت نشد.")

    # ---------------------------------------------------------
    # بخش ۵: تحلیل هوش مصنوعی
    # ---------------------------------------------------------
    elif choice == "📊 تحلیل هوش مصنوعی":
        st.subheader("🤖 تحلیل رفتاری و شلوغی باشگاه")
        hourly_df = get_hourly_occupancy(club_id)
        churn_df = predict_churn_risk(club_id)
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("### 📈 نمودار ساعات شلوغی")
            if not hourly_df.empty:
                st.bar_chart(data=hourly_df, x='hour', y='checkin_count', color="#1f77b4")
            else:
                st.info("هنوز ترددی ثبت نشده است.")
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
            else:
                st.success("هیچ عضوی در وضعیت ریسک ریزش قرار ندارد.")

    # ---------------------------------------------------------
    # بخش ۶: مدیریت و حذف
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # بخش ۷: ایجاد حساب جدید
    # ---------------------------------------------------------
    elif choice == "⚙️ ساخت باشگاه/مدیر جدید":
        st.subheader("👤 ساخت حساب باشگاه جدید")
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