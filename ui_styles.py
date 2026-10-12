"""
استایل‌های مشترک رابط کاربری سامانه.

- FONT_STYLE : بارگذاری فونت وزیرمتن و اعمال آن روی اجزای Streamlit (برای کل برنامه)
- AUTH_STYLE : استایل اختصاصی صفحه ورود / ثبت‌نام (فقط روی همان صفحه تزریق می‌شود)

پالت رنگی (هماهنگ با کارت سایدبار و فایل .streamlit/config.toml):
    پس‌زمینه  #0B1120     سطح کارت  #111A2E     مرز  #1E293B
    متن اصلی  #E2E8F0     متن کم‌رنگ #94A3B8
    تأکید     #38BDF8     دکمه #0EA5E9 → #2563EB
    ریسک      قرمز #EF4444 · زرد #F59E0B · سبز #10B981  (مثل سطح‌های ریسک ریزش)
"""

# -------------------------------------------------------------
# فونت: وزیرمتن (اگر لود نشد، Tahoma جایگزین می‌شود)
# آیکن‌های Material عمداً در لیست نیستند تا خراب نشوند.
# -------------------------------------------------------------
FONT_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700;800&display=swap');

.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input, .stApp textarea,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp [data-baseweb="tab"], .stApp [data-baseweb="select"], [data-baseweb="popover"],
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stMetricLabel"], .stApp [data-testid="stMetricValue"] {
    font-family: 'Vazirmatn', 'Tahoma', sans-serif !important;
}
</style>
"""

# -------------------------------------------------------------
# صفحه ورود / ثبت‌نام
# نکته: انتخابگرها عمداً با اولویت بالا (html body .stApp ...) نوشته شده‌اند تا
# بر استایل سراسری app.py (مثل .main .block-container) غلبه کنند.
# -------------------------------------------------------------
AUTH_STYLE = """
<style>
/* ستون باریک و وسط‌چین برای کارت ورود */
html body .stApp .block-container,
html body .stApp [data-testid="stMainBlockContainer"] {
    max-width: 460px !important;
    padding: 9vh 1rem 3rem !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

html body .stApp header[data-testid="stHeader"] {
    background: transparent !important;
}

/* --- هدر برند --- */
.auth-hero { text-align: center; margin-bottom: 22px; }
.auth-mark {
    width: 56px; height: 56px; margin: 0 auto 16px;
    display: grid; place-items: center;
    font-size: 28px; line-height: 1;
    background: #0F2A3F; border: 1px solid #1D4A66; border-radius: 16px;
}
.auth-title {
    margin: 0; font-size: 24px; font-weight: 800; line-height: 1.6; color: #F1F5F9;
}
.auth-sub {
    margin: 6px 0 0; font-size: 14px; line-height: 2; color: #94A3B8;
}

/* --- تب‌ها: دو گزینه هم‌عرض داخل یک کپسول ---
   انتخابگرها عمداً بر پایه نقش‌های ARIA (tablist / tab) هستند تا به نسخه Streamlit وابسته نباشند. */
html body .stApp [role="tablist"] {
    width: 100%; gap: 4px; padding: 4px;
    background: #0F172A; border: 1px solid #1E293B; border-radius: 12px;
}
html body .stApp [role="tab"] {
    flex: 1 1 0; justify-content: center; text-align: center !important;
    height: 40px; border-radius: 9px; color: #94A3B8; font-weight: 600;
}
html body .stApp [role="tab"] p { color: inherit !important; text-align: center !important; }
html body .stApp [role="tab"][aria-selected="true"] {
    background: rgba(56, 189, 248, 0.14); color: #38BDF8;
}
html body .stApp [data-baseweb="tab-highlight"],
html body .stApp [data-baseweb="tab-border"] { display: none !important; }

/* --- کارت فرم (بدون پس‌زمینه جدا تا فیلدهای ورودی با ظاهر پیش‌فرض Streamlit دیده شوند) --- */
html body .stApp [data-testid="stForm"] {
    background: transparent; border: 1px solid #1E293B; border-radius: 16px;
    padding: 22px 20px 20px;
}
html body .stApp [data-testid="stWidgetLabel"] p {
    font-size: 14px; font-weight: 600; color: #CBD5E1;
}
html body .stApp input::placeholder { color: #64748B !important; opacity: 1; }

/* --- دکمه اصلی (تمام‌عرض): همه ظرف‌های بین دکمه و فرم هم تمام‌عرض می‌شوند --- */
html body .stApp [data-testid="stFormSubmitButton"],
html body .stApp [data-testid="stFormSubmitButton"] > div,
html body .stApp [data-testid="stFormSubmitButton"] button {
    width: 100% !important;
}
html body .stApp [data-testid="stFormSubmitButton"] button {
    height: 46px; margin-top: 6px;
    border: 0 !important; border-radius: 10px !important;
    background: linear-gradient(135deg, #0EA5E9, #2563EB) !important;
    color: #FFFFFF !important; font-weight: 700 !important; font-size: 15px;
    justify-content: center;
}
html body .stApp [data-testid="stFormSubmitButton"] button * {
    text-align: center !important; justify-content: center; color: #FFFFFF !important;
}
html body .stApp [data-testid="stFormSubmitButton"] button:hover { filter: brightness(1.1); }
html body .stApp [data-testid="stFormSubmitButton"] button:focus-visible {
    outline: 2px solid #38BDF8; outline-offset: 2px;
}

/* --- معرفی کوتاه زیر فرم: رنگ نقطه‌ها همان سطح‌های ریسک ریزش است --- */
.auth-points {
    margin-top: 24px; padding: 0 6px;
    display: flex; flex-direction: column; gap: 10px;
}
.auth-point {
    display: flex; align-items: flex-start; gap: 10px;
    font-size: 13px; line-height: 1.9; color: #94A3B8;
}
.auth-point b { color: #CBD5E1; font-weight: 700; }
.auth-dot {
    flex: none; width: 8px; height: 8px; margin-top: 9px; border-radius: 50%;
}
</style>
"""

# محتوای هدر و معرفی (بدون تورفتگی و بدون خط خالی تا مارک‌داون آن را کد تلقی نکند)
AUTH_HERO_HTML = """
<div class="auth-hero">
<div class="auth-mark">🏋️</div>
<div class="auth-title">سامانه مدیریت هوشمند باشگاه</div>
<div class="auth-sub">اعضا، اشتراک‌ها و تردد را یک‌جا مدیریت کنید و ریزش اعضا را پیش از وقوع ببینید.</div>
</div>
"""

AUTH_POINTS_HTML = """
<div class="auth-points">
<div class="auth-point"><span class="auth-dot" style="background:#EF4444"></span><span><b>پیش‌بینی ریزش:</b> اعضایی که در خطر ترک باشگاه هستند را زودتر پیدا کنید.</span></div>
<div class="auth-point"><span class="auth-dot" style="background:#F59E0B"></span><span><b>اشتراک و تردد:</b> ثبت ورود و کسر جلسه فقط با چند کلیک.</span></div>
<div class="auth-point"><span class="auth-dot" style="background:#10B981"></span><span><b>ساعات شلوغی:</b> بدانید باشگاه چه ساعتی بیشترین تردد را دارد.</span></div>
</div>
"""

# -------------------------------------------------------------
# پنل اصلی: سایدبار + هدر صفحه + کارت‌های خلاصه
# عمداً به المان‌های داخلی Streamlit کم‌تر وابسته است:
#  - سایدبار با کلاس‌های st-key-* (از روی key دکمه‌ها) استایل می‌شود
#  - اگر انتخابگری در نسخه‌ای کار نکند، دکمه‌ها همچنان با ظاهر پیش‌فرض قابل استفاده‌اند
# -------------------------------------------------------------
PANEL_STYLE = """
<style>
/* --- کارت باشگاه در سایدبار --- */
.side-card {
    background: #111A2E; border: 1px solid #1E293B; border-radius: 14px;
    padding: 14px 16px; margin-bottom: 14px;
}
.side-label { font-size: 12px; color: #64748B; font-weight: 600; }
.side-club { font-size: 20px; font-weight: 800; color: #38BDF8; line-height: 1.6; word-break: break-word; }
.side-user { font-size: 12px; color: #94A3B8; margin-top: 2px; }

/* --- منوی ناوبری (هر آیتم یک دکمه با key=nav_*) --- */
[class*="st-key-nav_"], [class*="st-key-nav_"] > div, [class*="st-key-nav_"] button {
    width: 100% !important;
}
[class*="st-key-nav_"] button {
    justify-content: flex-start; height: 44px; border-radius: 10px;
    font-weight: 600; text-align: right !important;
}
[class*="st-key-nav_"] button * { text-align: right !important; color: inherit !important; }
[class*="st-key-nav_"] button[kind="secondary"],
[class*="st-key-nav_"] button[data-testid="stBaseButton-secondary"] {
    background: transparent !important; border: 1px solid transparent !important; color: #94A3B8 !important;
}
[class*="st-key-nav_"] button[kind="secondary"]:hover,
[class*="st-key-nav_"] button[data-testid="stBaseButton-secondary"]:hover {
    background: #111A2E !important; color: #E2E8F0 !important;
}
[class*="st-key-nav_"] button[kind="primary"],
[class*="st-key-nav_"] button[data-testid="stBaseButton-primary"] {
    background: rgba(56, 189, 248, 0.14) !important;
    border: 1px solid rgba(56, 189, 248, 0.35) !important; color: #38BDF8 !important;
}

/* --- دکمه خروج --- */
.st-key-logout, .st-key-logout > div, .st-key-logout button { width: 100% !important; }
.st-key-logout button {
    height: 42px; border-radius: 10px; background: transparent !important;
    border: 1px solid #3F1D2B !important; color: #FCA5A5 !important;
}
.st-key-logout button:hover { background: rgba(239, 68, 68, 0.10) !important; }

/* --- هدر صفحه --- */
.page-head { margin: 2px 0 18px; text-align: right; direction: rtl; }
.page-title { font-size: 26px; font-weight: 800; color: #F1F5F9; line-height: 1.6; }
.page-sub { font-size: 14px; color: #94A3B8; margin-top: 2px; }

/* --- شمارنده نتایج؛ فاصله پایین عمدی است (نوار ابزار جدول روی لبه بالای آن می‌نشیند) --- */
.result-count { font-size: 13px; color: #94A3B8; margin: 2px 0 28px; text-align: right; direction: rtl; }

/* --- کارت‌های خلاصه --- */
.kpi-grid {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px; margin: 0 0 18px; direction: rtl;
}
.kpi { background: #111A2E; border: 1px solid #1E293B; border-radius: 14px; padding: 14px 16px; }
.kpi-label { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: #94A3B8; }
.kpi-dot { flex: none; width: 8px; height: 8px; border-radius: 50%; }
.kpi-value { font-size: 30px; font-weight: 800; line-height: 1.5; color: #F1F5F9; margin-top: 4px; }
.kpi-note { font-size: 12px; color: #64748B; }
@media (max-width: 760px) {
    .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
"""
