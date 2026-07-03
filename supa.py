"""
supa.py — จัดการการเชื่อมต่อ Supabase
อ่านค่า URL/Key จาก Streamlit secrets (บน Cloud) หรือ environment variable (ในเครื่อง)

มี 2 client:
  - auth_client()    : ใช้ anon key สำหรับ ล็อกอิน/ส่งเมลรีเซ็ตรหัส (ระบุตัวผู้ใช้)
  - service_client() : ใช้ service key สำหรับอ่าน/เขียนข้อมูลและงาน admin
"""
import os

try:
    import streamlit as st
except Exception:
    st = None


def _secret(name, default=""):
    """อ่านค่า config จาก st.secrets ก่อน ถ้าไม่มีลอง environment variable"""
    if st is not None:
        try:
            if name in st.secrets:
                return st.secrets[name]
        except Exception:
            pass
    return os.environ.get(name, default)


def get_url():
    # ตัด /rest/v1/ ท้ายออก ถ้าเผลอใส่มา — create_client ต้องการ URL ฐานเท่านั้น
    url = _secret("SUPABASE_URL", "").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return url


def _make_client(key):
    from supabase import create_client  # import ตอนใช้จริง (กัน import พังถ้ายังไม่ลงไลบรารี)
    return create_client(get_url(), key)


# ใช้ st.cache_resource เพื่อไม่สร้าง client ใหม่ทุกครั้งที่รีเฟรช
def _cache(fn):
    if st is not None:
        return st.cache_resource(fn)
    return fn


@_cache
def service_client():
    return _make_client(_secret("SUPABASE_SERVICE_KEY"))


@_cache
def auth_client():
    return _make_client(_secret("SUPABASE_ANON_KEY"))


def is_configured():
    """เช็กว่าตั้งค่า secrets ครบหรือยัง"""
    return bool(get_url() and _secret("SUPABASE_ANON_KEY") and _secret("SUPABASE_SERVICE_KEY"))
