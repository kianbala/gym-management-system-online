import streamlit as st

from auth_ui import render_auth_page
from ui_styles import FONT_STYLE
from panel_ui import render_sidebar, render_dashboard
from member_ui import render_add_member
from checkin_ui import render_checkin
from assign_ui import render_assign
from manage_ui import render_manage
from stats_ui import render_stats

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

    /* ۲-ب. وقتی منو بسته است، خود کادر سایدبار هم حذف شود؛ وگرنه نوار باریکی از آن (با متن‌های ریز عمودی) روی صفحه می‌ماند.
       چند قانون جدا نوشته شده تا با نسخه‌های مختلف Streamlit کار کند؛ هر قانون مستقل است و اگر مرورگر یکی را نفهمد بقیه اثر می‌کنند. */

    /* الف) نسخه‌هایی که وضعیت را با aria-expanded نشان می‌دهند */
    [data-testid="stSidebar"][aria-expanded="false"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        border: 0 !important;
        box-shadow: none !important;
    }

    /* ب) دکمه «باز کردن منو» فقط وقتی هست که منو بسته است؛ پس اگر هست، کادر سایدبار را پنهان کن
          (:not([aria-expanded="true"]) تضمین می‌کند منوی باز هیچ‌وقت پنهان نشود) */
    .stApp:has([data-testid="stSidebarCollapsedControl"]) [data-testid="stSidebar"]:not([aria-expanded="true"]) {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        border: 0 !important;
        box-shadow: none !important;
    }
    .stApp:has([data-testid="stExpandSidebarButton"]) [data-testid="stSidebar"]:not([aria-expanded="true"]) {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        border: 0 !important;
        box-shadow: none !important;
    }
    .stApp:has([data-testid="collapsedControl"]) [data-testid="stSidebar"]:not([aria-expanded="true"]) {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        border: 0 !important;
        box-shadow: none !important;
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
        render_stats(club_id)

    elif choice == "مدیریت و حذف":
        render_manage(club_id)
