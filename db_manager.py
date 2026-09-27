import streamlit as st
import pandas as pd
from supabase import create_client, Client

@st.cache_resource
def get_supabase_client() -> Client:
    """برقراری اتصال امن به دیتابیس آنلاین Supabase"""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def get_members_data() -> pd.DataFrame:
    """دریافت کامل داده‌های اعضا"""
    try:
        supabase = get_supabase_client()
        response = supabase.table("members").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"خطا در دریافت داده‌های اعضا: {e}")
        return pd.DataFrame()

def get_checkins_data() -> pd.DataFrame:
    """دریافت داده‌های تردد و حضور اعضا"""
    try:
        supabase = get_supabase_client()
        response = supabase.table("checkins").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"خطا در دریافت داده‌های تردد: {e}")
        return pd.DataFrame()