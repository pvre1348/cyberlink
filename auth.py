"""
auth.py — ระบบผู้ใช้ของ CyberLink (ใช้ Supabase Auth)
  - ล็อกอิน / ลืมรหัสผ่าน (ผ่านอีเมล)
  - สมัครด้วย invite code เท่านั้น จำกัดผู้ใช้รวมไม่เกิน MAX_USERS คน
  - บทบาท admin / user (เก็บในตาราง profiles)
"""
import secrets as pysecrets
import string
from datetime import datetime, timezone

import supa

MAX_USERS = 20   # เพดานจำนวนบัญชี


def _svc():
    return supa.service_client()


def _auth():
    return supa.auth_client()


# ---------------- ล็อกอิน ----------------
def sign_in(email, password):
    """คืน dict {ok, user, role, error}"""
    try:
        res = _auth().auth.sign_in_with_password({"email": email.strip(), "password": password})
        if not res.user:
            return {"ok": False, "error": "อีเมลหรือรหัสผ่านไม่ถูกต้อง"}
        role = get_role(res.user.id)
        return {"ok": True,
                "user": {"id": res.user.id, "email": res.user.email},
                "role": role}
    except Exception as e:
        return {"ok": False, "error": f"เข้าสู่ระบบไม่สำเร็จ: {e}"}


def reset_password(email):
    try:
        _auth().auth.reset_password_for_email(email.strip())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_role(user_id):
    try:
        r = _svc().table("profiles").select("role").eq("id", user_id).execute()
        if r.data:
            return r.data[0].get("role", "user")
    except Exception:
        pass
    return "user"


# ---------------- นับจำนวนผู้ใช้ ----------------
def user_count():
    try:
        r = _svc().table("profiles").select("id").execute()
        return len(r.data or [])
    except Exception:
        return 0


# ---------------- สมัครสมาชิก (ต้องมี invite code) ----------------
def sign_up(email, password, invite_code):
    """สร้างบัญชีใหม่ ถ้า invite code ถูกต้อง/ยังไม่ถูกใช้ และยังไม่เกินเพดาน"""
    email = email.strip().lower()
    code = (invite_code or "").strip().upper()
    if not email or not password:
        return {"ok": False, "error": "กรุณากรอกอีเมลและรหัสผ่าน"}
    if len(password) < 8:
        return {"ok": False, "error": "รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร"}

    # ตรวจเพดานจำนวนผู้ใช้
    if user_count() >= MAX_USERS:
        return {"ok": False, "error": f"ระบบเต็มแล้ว (จำกัด {MAX_USERS} บัญชี) ติดต่อผู้ดูแล"}

    # ตรวจ invite code
    try:
        r = _svc().table("invite_codes").select("*").eq("code", code).execute()
    except Exception as e:
        return {"ok": False, "error": f"ตรวจสอบรหัสเชิญไม่สำเร็จ: {e}"}
    if not r.data:
        return {"ok": False, "error": "รหัสเชิญไม่ถูกต้อง"}
    if r.data[0].get("used_by"):
        return {"ok": False, "error": "รหัสเชิญนี้ถูกใช้ไปแล้ว"}

    # สร้างผู้ใช้ผ่าน admin API (ยืนยันอีเมลอัตโนมัติ ล็อกอินได้ทันที)
    try:
        created = _svc().auth.admin.create_user({
            "email": email, "password": password, "email_confirm": True})
        new_id = created.user.id
    except Exception as e:
        return {"ok": False, "error": f"สร้างบัญชีไม่สำเร็จ (อีเมลอาจซ้ำ): {e}"}

    # ทำเครื่องหมายว่า invite code ถูกใช้แล้ว
    try:
        _svc().table("invite_codes").update({
            "used_by": new_id,
            "used_at": datetime.now(timezone.utc).isoformat()}).eq("code", code).execute()
    except Exception:
        pass

    return {"ok": True}


# ---------------- invite code (admin) ----------------
def _gen_code(n=8):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(pysecrets.choice(alphabet) for _ in range(n))


def create_invite(admin_id):
    """สร้างรหัสเชิญใหม่ (ถ้ายังไม่เกินเพดาน จำนวนผู้ใช้ + รหัสที่ยังไม่ถูกใช้)"""
    used_or_pending = user_count() + count_unused_invites()
    if used_or_pending >= MAX_USERS:
        return {"ok": False, "error": f"เต็มเพดาน {MAX_USERS} แล้ว ลบผู้ใช้เดิมหรือยกเลิกรหัสที่ค้างก่อน"}
    code = _gen_code()
    try:
        _svc().table("invite_codes").insert({"code": code, "created_by": admin_id}).execute()
        return {"ok": True, "code": code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def count_unused_invites():
    try:
        r = _svc().table("invite_codes").select("code").is_("used_by", "null").execute()
        return len(r.data or [])
    except Exception:
        return 0


def list_invites():
    try:
        r = _svc().table("invite_codes").select("*").order("created_at", desc=True).execute()
        return r.data or []
    except Exception:
        return []


def revoke_invite(code):
    try:
        _svc().table("invite_codes").delete().eq("code", code).is_("used_by", "null").execute()
        return True
    except Exception:
        return False


# ---------------- จัดการผู้ใช้ (admin) ----------------
def list_users():
    try:
        r = _svc().table("profiles").select("*").order("created_at").execute()
        return r.data or []
    except Exception:
        return []


def set_role(user_id, role):
    try:
        _svc().table("profiles").update({"role": role}).eq("id", user_id).execute()
        return True
    except Exception:
        return False


def delete_user(user_id):
    """ลบบัญชีผู้ใช้ (profiles จะถูกลบตาม cascade)"""
    try:
        _svc().auth.admin.delete_user(user_id)
        return True
    except Exception:
        return False
