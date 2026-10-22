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

/* --- فرم‌های پنل (کارت + دکمه اصلی تمام‌عرض) --- */
html body .stApp [data-testid="stForm"] {
    border: 1px solid #1E293B; border-radius: 16px; padding: 22px 20px 20px;
}
html body .stApp [data-testid="stFormSubmitButton"],
html body .stApp [data-testid="stFormSubmitButton"] > div,
html body .stApp [data-testid="stFormSubmitButton"] button { width: 100% !important; }
html body .stApp [data-testid="stFormSubmitButton"] button {
    height: 46px; margin-top: 6px; border: 0 !important; border-radius: 10px !important;
    background: linear-gradient(135deg, #0EA5E9, #2563EB) !important;
    color: #FFFFFF !important; font-weight: 700 !important; font-size: 15px; justify-content: center;
}
html body .stApp [data-testid="stFormSubmitButton"] button * { text-align: center !important; color: #FFFFFF !important; }
html body .stApp [data-testid="stFormSubmitButton"] button:hover { filter: brightness(1.1); }

/* --- پیام خطای زیر هر فیلد --- */
.field-error { color: #FCA5A5; font-size: 12.5px; line-height: 1.8; margin: -4px 0 6px; text-align: right; direction: rtl; }

/* --- کارت تأیید ثبت و کارت هشدار --- */
.ok-card, .warn-card {
    display: flex; align-items: flex-start; gap: 14px; direction: rtl;
    border-radius: 14px; padding: 14px 16px; margin-bottom: 12px;
}
.ok-card { background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.35); }
.warn-card { background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.35); }
.ok-icon, .warn-icon {
    flex: none; width: 36px; height: 36px; border-radius: 50%;
    display: grid; place-items: center; font-weight: 800; font-size: 18px;
}
.ok-icon { background: #10B981; color: #04130D; }
.warn-icon { background: #F59E0B; color: #1C1203; }
.ok-title { font-size: 16px; font-weight: 800; color: #ECFDF5; line-height: 1.7; }
.warn-title { font-size: 16px; font-weight: 800; color: #FEF3C7; line-height: 1.7; }
.ok-sub { font-size: 13px; color: #A7F3D0; line-height: 2; }
.warn-sub { font-size: 13px; color: #FDE68A; line-height: 2; }

/* --- فهرست آخرین اعضا --- */
.recent { background: #111A2E; border: 1px solid #1E293B; border-radius: 16px; padding: 16px; direction: rtl; }
.recent-title { font-size: 14px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px; }
.recent-empty { font-size: 13px; color: #64748B; padding: 10px 0; }
.recent-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; }
.recent-item + .recent-item { border-top: 1px solid #1E293B; }
.recent-new { background: rgba(56, 189, 248, 0.07); border-radius: 10px; padding-left: 8px; padding-right: 8px; margin: 0 -8px; }
.avatar {
    flex: none; width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center;
    background: #0F2A3F; color: #38BDF8; font-weight: 800;
}
.r-main { flex: 1; min-width: 0; }
.r-name { font-size: 14px; font-weight: 700; color: #E2E8F0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.r-sub { font-size: 12px; color: #64748B; }
.chip { font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
.chip-green { background: rgba(16, 185, 129, 0.14); color: #34D399; }
.chip-red { background: rgba(239, 68, 68, 0.14); color: #F87171; }
.chip-gray { background: rgba(148, 163, 184, 0.14); color: #94A3B8; }

/* --- صفحه ثبت ورود: کارت عضو، نوار جلسات، پنل ورودهای امروز --- */
.ci-card { background: #111A2E; border: 1px solid #1E293B; border-radius: 14px; padding: 14px 16px; direction: rtl; }
.ci-card-off { background: #0E1626; }
.ci-top { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.ci-name { font-size: 16px; font-weight: 800; color: #F1F5F9; line-height: 1.7; }
.ci-meta { font-size: 12.5px; color: #64748B; }
.ci-line { display: flex; align-items: center; gap: 12px; margin-top: 6px; font-size: 12.5px; color: #94A3B8; }
.ci-bar { flex: 1; min-width: 80px; height: 6px; border-radius: 999px; background: #1E293B; overflow: hidden; }
.ci-bar-fill { height: 100%; border-radius: 999px; background: #10B981; }
.ci-bar-low .ci-bar-fill { background: #F59E0B; }
.ci-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.chip-amber { background: rgba(245, 158, 11, 0.14); color: #FBBF24; }
.chip-blue { background: rgba(56, 189, 248, 0.14); color: #38BDF8; }
.ci-empty {
    border: 1px dashed #243049; border-radius: 14px; padding: 22px 18px; direction: rtl;
    font-size: 13.5px; line-height: 2; color: #94A3B8; text-align: center;
}
.today { background: #111A2E; border: 1px solid #1E293B; border-radius: 16px; padding: 16px; direction: rtl; margin-bottom: 8px; }
.today-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.today-title { font-size: 14px; font-weight: 700; color: #CBD5E1; }
.today-count { font-size: 12px; font-weight: 700; color: #38BDF8; }
.today-empty { font-size: 13px; color: #64748B; padding: 10px 0; }
.today-item { display: flex; align-items: center; gap: 12px; padding: 8px 0; font-size: 13.5px; }
.today-item + .today-item { border-top: 1px solid #1E293B; }
.today-time { flex: none; min-width: 44px; color: #64748B; font-size: 12.5px; }
.today-name { color: #E2E8F0; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.today-undo { font-size: 13px; color: #CBD5E1; direction: rtl; }

/* --- صفحه تخصیص بسته --- */
.as-label { font-size: 13px; font-weight: 700; color: #94A3B8; margin: 2px 0; text-align: right; direction: rtl; }
.sum-card {
    background: rgba(56, 189, 248, 0.07); border: 1px solid rgba(56, 189, 248, 0.30); border-radius: 14px;
    padding: 12px 16px; color: #BAE6FD; font-size: 13.5px; line-height: 2; direction: rtl;
}
.sum-card b { color: #E0F2FE; }
.hist-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; direction: rtl; }
.hist-item + .hist-item { border-top: 1px solid #1E293B; }
.hist-main { flex: 1; min-width: 0; }
.hist-title { font-size: 14px; font-weight: 700; color: #E2E8F0; }
.hist-sub { font-size: 12px; color: #64748B; line-height: 1.8; }
.guide-step { display: flex; align-items: flex-start; gap: 12px; padding: 8px 0; font-size: 13.5px; line-height: 1.9; color: #94A3B8; direction: rtl; }
.guide-num {
    flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center;
    background: #0F2A3F; color: #38BDF8; font-weight: 800; font-size: 13px;
}
.guide-note { margin-top: 8px; padding-top: 10px; border-top: 1px solid #1E293B; font-size: 12.5px; line-height: 1.9; color: #64748B; }

/* --- دکمه‌های اصلی در بخش اصلی صفحه (غیر از سایدبار): کنتراست بهتر --- */
html body .stApp [data-testid="stMain"] button[kind="primary"],
html body .stApp [data-testid="stMain"] button[data-testid="stBaseButton-primary"],
html body .stApp section.main button[kind="primary"] {
    background: linear-gradient(135deg, #0EA5E9, #2563EB) !important; border: 0 !important;
    color: #FFFFFF !important; font-weight: 700 !important;
}
html body .stApp [data-testid="stMain"] button[kind="primary"] *,
html body .stApp [data-testid="stMain"] button[data-testid="stBaseButton-primary"] * { color: #FFFFFF !important; }
html body .stApp [data-testid="stMain"] button[kind="primary"]:hover,
html body .stApp [data-testid="stMain"] button[data-testid="stBaseButton-primary"]:hover { filter: brightness(1.1); }

/* --- صفحه آمار: عنوان بخش‌ها، توزیع ریسک، کارت‌های پیگیری، نمودارها --- */
.sec-head { margin: 26px 0 10px; direction: rtl; text-align: right; }
.sec-title { font-size: 19px; font-weight: 800; color: #F1F5F9; line-height: 1.7; }
.sec-sub { font-size: 13px; color: #94A3B8; line-height: 1.9; }

.rk-card { background: #111A2E; border: 1px solid #1E293B; border-radius: 14px; padding: 14px 16px; margin-bottom: 8px; direction: rtl; }
.rk-title { font-size: 14px; font-weight: 700; color: #CBD5E1; margin-bottom: 10px; }
.rk-sub { font-size: 12px; font-weight: 500; color: #64748B; margin-right: 8px; }
.rk-bar { display: flex; height: 14px; border-radius: 999px; overflow: hidden; background: #1E293B; gap: 2px; direction: rtl; }
.rk-seg { height: 100%; }
.rk-legend { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 10px; font-size: 12.5px; color: #94A3B8; }
.rk-leg { display: inline-flex; align-items: center; gap: 8px; }

.fu-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 6px 0 8px; direction: rtl; }
@media (max-width: 900px) { .fu-grid { grid-template-columns: minmax(0, 1fr); } }
.fu-card { background: #111A2E; border: 1px solid #1E293B; border-radius: 14px; padding: 14px 16px; direction: rtl; }
.fu-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.fu-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
a.act, a.act:visited {
    display: inline-flex; align-items: center; justify-content: center; min-width: 76px; height: 36px; padding: 0 14px;
    border-radius: 10px; border: 1px solid #243049; background: #0E1626; color: #E2E8F0 !important;
    font-size: 13px; font-weight: 700; text-decoration: none !important;
}
a.act:hover { border-color: #38BDF8; color: #38BDF8 !important; }
a.act-wa { background: rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.40); color: #34D399 !important; }
.fu-nophone { font-size: 12.5px; color: #64748B; line-height: 36px; }
.fu-msg { margin-top: 10px; font-size: 12.5px; color: #94A3B8; }
.fu-msg summary { cursor: pointer; color: #64748B; }
.fu-msg div { margin-top: 6px; line-height: 2; padding: 8px 10px; background: #0E1626; border-radius: 8px; user-select: all; }

.chart-card { background: #111A2E; border: 1px solid #1E293B; border-radius: 16px; padding: 16px 16px 12px; margin-bottom: 8px; direction: rtl; }
.chart-title { font-size: 14px; font-weight: 700; color: #CBD5E1; margin-bottom: 12px; }
.chart-note { margin-top: 10px; font-size: 13px; line-height: 2; color: #94A3B8; min-height: 20px; }
.chart-note b { color: #E2E8F0; }
.bars { display: flex; align-items: stretch; gap: 6px; direction: rtl; }
.bar-col { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; }
.bar-val { font-size: 11px; color: #94A3B8; line-height: 1.6; min-height: 18px; }
.bar-track { flex: 1; width: 100%; display: flex; align-items: flex-end; }
.bar-fill { width: 100%; min-height: 2px; border-radius: 6px 6px 2px 2px; background: #2A4A7A; }
.bar-hi { background: #38BDF8; }
.bar-label { margin-top: 6px; font-size: 11px; color: #64748B; line-height: 1.4; }

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

/* --- صفحه مدیریت و حذف: کارت عضو، کارت خطا، منطقه خطر، دکمه‌های قرمز --- */
.mg-card {
    display: flex; align-items: flex-start; gap: 12px; direction: rtl;
    background: #111A2E; border: 1px solid #1E293B; border-radius: 14px; padding: 14px 16px;
}
.mg-card-off { background: #0E1626; }
.mg-main { flex: 1; min-width: 0; }
.mg-name { font-size: 16px; font-weight: 800; color: #F1F5F9; line-height: 1.7; word-break: break-word; }
.mg-meta { font-size: 12.5px; color: #64748B; line-height: 1.9; }
.mg-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }

.err-card {
    display: flex; align-items: flex-start; gap: 14px; direction: rtl;
    border-radius: 14px; padding: 14px 16px; margin: 8px 0 12px;
    background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.40);
}
.err-icon {
    flex: none; width: 36px; height: 36px; border-radius: 50%;
    display: grid; place-items: center; font-weight: 800; font-size: 18px; background: #EF4444; color: #1F0707;
}
.err-title { font-size: 16px; font-weight: 800; color: #FEE2E2; line-height: 1.7; }
.err-sub { font-size: 13px; color: #FCA5A5; line-height: 2; }

.dz-card {
    direction: rtl; border: 1px solid rgba(239, 68, 68, 0.45); border-radius: 16px; padding: 16px 18px;
    background: rgba(239, 68, 68, 0.05); margin-bottom: 14px;
}
.dz-head { display: flex; align-items: flex-start; gap: 14px; }
.dz-title { font-size: 17px; font-weight: 800; color: #FEE2E2; line-height: 1.7; }
.dz-sub { font-size: 13px; color: #FCA5A5; line-height: 2; }
.dz-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.dz-stat { background: #111A2E; border: 1px solid #1E293B; border-radius: 12px; padding: 10px 12px; text-align: center; }
.dz-stat b { display: block; font-size: 22px; font-weight: 800; color: #F1F5F9; line-height: 1.5; }
.dz-stat span { font-size: 12px; color: #94A3B8; }

/* دکمه‌های حذف (کلید mgd_*): خط‌دور قرمز؛ دکمه‌های تأیید نهایی خطرناک (کلید mgx_*): قرمز توپر */
[class*="st-key-mgd_"], [class*="st-key-mgd_"] > div, [class*="st-key-mgd_"] button { width: 100% !important; }
[class*="st-key-mgd_"] button {
    background: transparent !important; border: 1px solid #3F1D2B !important; color: #FCA5A5 !important;
}
[class*="st-key-mgd_"] button * { color: #FCA5A5 !important; }
[class*="st-key-mgd_"] button:hover { background: rgba(239, 68, 68, 0.10) !important; }
html body .stApp [data-testid="stMain"] [class*="st-key-mgx_"] button,
html body .stApp [data-testid="stMain"] [class*="st-key-mgx_"] button[kind="primary"],
html body .stApp [data-testid="stMain"] [class*="st-key-mgx_"] button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #EF4444, #B91C1C) !important; border: 0 !important;
    color: #FFFFFF !important; font-weight: 700 !important;
}
html body .stApp [data-testid="stMain"] [class*="st-key-mgx_"] button * { color: #FFFFFF !important; }
html body .stApp [data-testid="stMain"] [class*="st-key-mgx_"] button:disabled { opacity: 0.4 !important; }
</style>
"""
