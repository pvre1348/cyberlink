"""
app.py — CyberLink ระบบคดีและพื้นที่เสี่ยง (Supabase + ระบบล็อกอิน)
ธีมมืดสไตล์ ArcGIS Dashboards (Esri)

- ต้องล็อกอินก่อนใช้งาน (สมัครด้วย invite code เท่านั้น จำกัด 20 บัญชี)
- บทบาท admin (ทุกอย่าง) / user (บันทึก-แก้คดี ค้นหา ดูแผนที่)
- ข้อมูลอยู่บน Supabase → ทุกอุปกรณ์เห็นข้อมูลชุดเดียวกัน
"""
import io
from datetime import date

import pandas as pd
import streamlit as st

import supa
import auth
import database as db
import seed_data
import geo
import map_view

try:
    import folium  # noqa
    from streamlit_folium import st_folium
    HAS_MAP = True
except Exception:
    HAS_MAP = False

st.set_page_config(page_title="ระบบคดีและพื้นที่เสี่ยง", page_icon="🛡️", layout="wide")

# ---------------------------------------------------------------- ค่าคงที่
ONLINE_TYPES = ["หลอกลงทุน", "แก๊งคอลเซ็นเตอร์", "หลอกซื้อขายออนไลน์",
                "Romance Scam", "หลอกกู้เงิน", "อื่น ๆ (ระบุเอง)"]
PHYSICAL_TYPES = ["ลักทรัพย์", "วิ่งราวทรัพย์", "ชิงทรัพย์", "ปล้นทรัพย์",
                  "ก่อจลาจล/ความวุ่นวาย", "อื่น ๆ (ระบุเอง)"]
OTHER = "อื่น ๆ (ระบุเอง)"
TIME_BUCKETS = ["ไม่ระบุ", "เช้า (06-12)", "บ่าย (12-18)", "ค่ำ (18-24)", "ดึก (00-06)"]
DIRECTIONS = ["กลาง", "เหนือ", "ใต้", "ตะวันออก", "ตะวันตก",
              "ตะวันออกเฉียงเหนือ", "ตะวันออกเฉียงใต้",
              "ตะวันตกเฉียงเหนือ", "ตะวันตกเฉียงใต้"]
RISK_LEVELS = ["สูง", "ปานกลาง", "ต่ำ"]
LUMP = (13.7305, 100.5460)
CAT_ONLINE = "cyber"
CAT_PHYSICAL = "physical"

# ---------------------------------------------------------------- ธีมมืด Esri
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Prompt:wght@400;500;600;700&family=IBM+Plex+Sans+Thai:wght@300;400;500;600&display=swap');
:root{--ink-0:#0F1A26;--ink-1:#172230;--ink-2:#1B2735;--ink-3:#223145;--line:#2A3A4E;
  --esri:#0079C1;--signal:#E0533D;--gold:#F0A500;--green:#2E7D52;--text-1:#F0F4F9;--text-2:#8FA3B5;}
html,body,[class*="css"]{font-family:'IBM Plex Sans Thai',sans-serif;}
h1,h2,h3,h4,h5{font-family:'Prompt',sans-serif;color:var(--text-1);letter-spacing:.2px;}
.stApp{background:var(--ink-2);}
.block-container{padding-top:4.5rem;padding-bottom:3rem;max-width:1340px;}
header[data-testid="stHeader"]{background:transparent !important;}
.esri-topbar{background:var(--ink-0);border-bottom:3px solid var(--esri);padding:12px 22px;
  margin:0 0 18px;border-radius:10px;display:flex;align-items:center;gap:14px;}
.esri-topbar .logo{width:26px;height:26px;background:var(--esri);border-radius:4px;
  display:flex;align-items:center;justify-content:center;color:#fff;}
.esri-topbar .title{color:#fff;font-weight:500;font-size:15px;font-family:'Prompt';}
.esri-topbar .sub{color:var(--text-2);font-size:12px;}
.esri-topbar .who{margin-left:auto;color:var(--text-2);font-size:12px;text-align:right;}
.metric-card{background:var(--ink-3);border-radius:8px;padding:14px 16px;position:relative;
  overflow:hidden;color:var(--text-1);}
.metric-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--esri);}
.metric-card.signal:before{background:var(--signal);}
.metric-card.gold:before{background:var(--gold);}
.metric-card.green:before{background:var(--green);}
.metric-card .label{font-size:.78rem;color:var(--text-2);font-weight:500;}
.metric-card .value{font-size:1.7rem;font-weight:600;color:#fff;font-family:'Prompt';line-height:1.25;margin-top:2px;}
.section-title{font-family:'Prompt';font-weight:600;color:var(--text-1);font-size:1.05rem;
  margin:10px 0 12px;padding-left:10px;border-left:3px solid var(--esri);}
.badge{padding:3px 14px;border-radius:20px;font-weight:600;font-size:.82rem;}
.badge.high{background:#4A1B1B;color:#FF9C97;}.badge.mid{background:#453207;color:#FFD37A;}
.badge.low{background:#1E3B2B;color:#8FD5AB;}
.badge.admin{background:#0A3A5C;color:#7FC9F5;}.badge.user{background:#2A3A4E;color:#B8C6D6;}
.link-alert{background:#2B1F1B;border:1px solid var(--signal);border-left:5px solid var(--signal);
  border-radius:10px;padding:14px 18px;margin:10px 0;color:var(--text-1);}
.link-alert h3{color:#FFB29F;margin:0 0 4px;font-size:1.05rem;}
.link-alert p{margin:0;color:var(--text-2);font-size:.9rem;}
.shared-chip{display:inline-block;background:var(--esri);color:#fff;padding:3px 10px;border-radius:6px;
  font-size:.8rem;margin:3px 5px 3px 0;}
.link-row{padding:9px 0;border-bottom:1px solid var(--line);color:var(--text-1);}
section[data-testid="stSidebar"]{background:var(--ink-1);border-right:1px solid var(--line);}
section[data-testid="stSidebar"] *{color:var(--text-1);}
.guide-card{background:var(--ink-1);border-radius:10px;padding:18px 22px;margin-bottom:14px;
  border-left:4px solid var(--esri);color:var(--text-1);}
.guide-card h3{color:#fff;margin:0 0 8px;font-size:1.1rem;}
.guide-card p,.guide-card li{color:var(--text-1);font-size:.95rem;line-height:1.7;}
.guide-card code{background:var(--ink-3);color:#FFD37A;padding:1px 6px;border-radius:3px;font-size:.85rem;}
.guide-step{display:inline-block;background:var(--esri);color:#fff;width:22px;height:22px;border-radius:50%;
  text-align:center;font-weight:600;font-size:.85rem;margin-right:8px;}
.hint{color:var(--text-2);font-size:.88rem;margin:-6px 0 12px 12px;}
.login-box{max-width:420px;margin:3vh auto 0;background:var(--ink-1);border:1px solid var(--line);
  border-radius:14px;padding:26px 28px;border-top:4px solid var(--esri);}
.login-box h2{color:#fff;margin:0 0 4px;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
SHIELD = ('<svg width="16" height="16" viewBox="0 0 24 24">'
          '<path d="M12 2L4 5v6c0 5 3.5 8.5 8 11 4.5-2.5 8-6 8-11V5l-8-3z" fill="#fff"/></svg>')


# ---------------------------------------------------------------- helpers
def metric_card(label, value, style=""):
    return f'<div class="metric-card {style}"><div class="label">{label}</div><div class="value">{value}</div></div>'


def section_title(t):
    st.markdown(f'<div class="section-title">{t}</div>', unsafe_allow_html=True)


def hint(t):
    st.markdown(f'<div class="hint">{t}</div>', unsafe_allow_html=True)


def risk_badge(level):
    cls = {"สูง": "high", "ปานกลาง": "mid", "ต่ำ": "low"}.get(level, "low")
    return f'<span class="badge {cls}">{level}</span>'


def parse_lines(text):
    return [l.strip() for l in (text or "").splitlines() if l.strip()]


def render_links(links):
    for lk in links:
        chips = "".join(f'<span class="shared-chip">{s["label"]}: {s["value"]}</span>'
                        for s in lk["shared"])
        st.markdown(f'<div class="link-row">🔸 <b>{lk["case_number"]}</b> '
                    f'({lk["station_code"]} · {lk["crime_type"]})<br>{chips}</div>',
                    unsafe_allow_html=True)


def category_label(cat):
    return "ออนไลน์" if cat == CAT_ONLINE else "ในพื้นที่"


def current_user():
    return st.session_state.get("auth")


def is_admin():
    u = current_user()
    return bool(u and u.get("role") == "admin")


# ================================================================
# หน้าล็อกอิน (แสดงก่อนเข้าระบบ)
# ================================================================
def login_screen():
    st.markdown(f"""<div class="esri-topbar"><div class="logo">{SHIELD}</div>
      <div><div class="title">CyberLink · ระบบคดีและพื้นที่เสี่ยง</div>
      <div class="sub">กรุณาเข้าสู่ระบบเพื่อใช้งาน</div></div></div>""", unsafe_allow_html=True)

    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    tab_in, tab_up, tab_forgot = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก", "ลืมรหัสผ่าน"])

    with tab_in:
        email = st.text_input("อีเมล", key="li_email")
        pw = st.text_input("รหัสผ่าน", type="password", key="li_pw")
        if st.button("เข้าสู่ระบบ", use_container_width=True):
            res = auth.sign_in(email, pw)
            if res["ok"]:
                st.session_state["auth"] = {"id": res["user"]["id"],
                                            "email": res["user"]["email"], "role": res["role"]}
                st.rerun()
            else:
                st.error(res["error"])

    with tab_up:
        st.caption("สมัครได้เฉพาะผู้มีรหัสเชิญจากผู้ดูแลระบบ")
        su_email = st.text_input("อีเมล", key="su_email")
        su_pw = st.text_input("รหัสผ่าน (อย่างน้อย 8 ตัว)", type="password", key="su_pw")
        su_code = st.text_input("รหัสเชิญ (Invite code)", key="su_code")
        if st.button("สมัครสมาชิก", use_container_width=True):
            res = auth.sign_up(su_email, su_pw, su_code)
            if res["ok"]:
                st.success("สมัครสำเร็จ! กลับไปที่แท็บ 'เข้าสู่ระบบ' เพื่อล็อกอิน")
            else:
                st.error(res["error"])

    with tab_forgot:
        st.caption("ระบบจะส่งลิงก์รีเซ็ตรหัสผ่านไปที่อีเมลของคุณ")
        fp_email = st.text_input("อีเมล", key="fp_email")
        if st.button("ส่งลิงก์รีเซ็ตรหัสผ่าน", use_container_width=True):
            res = auth.reset_password(fp_email)
            if res["ok"]:
                st.success("ส่งลิงก์แล้ว ตรวจสอบอีเมลของคุณ")
            else:
                st.error(res["error"])
    st.markdown('</div>', unsafe_allow_html=True)


# ================================================================
# ฟอร์มคดี (ปักหมุดแผนที่)
# ================================================================
def case_form(category, prefill=None, key="form", submit_label="บันทึก"):
    p = prefill or {}
    types = ONLINE_TYPES if category == CAT_ONLINE else PHYSICAL_TYPES
    cur_type = p.get("crime_type")
    type_idx = types.index(cur_type) if cur_type in types else 0
    init_date = date.fromisoformat(p["report_date"]) if p.get("report_date") else date.today()
    ind = p.get("indicators", {})

    stations = db.get_stations()
    st_labels = [f'{s["code"]} — {s["name"]}' for s in stations]
    st_ids = [s["station_id"] for s in stations]
    st_idx = st_ids.index(p["station_id"]) if p.get("station_id") in st_ids else 0

    section_title("📍 ปักหมุดจุดเกิดเหตุบนแผนที่")
    hint("คลิกที่ใดในแผนที่ = พิกัดถูกกรอกให้อัตโนมัติ (คลิกใหม่เพื่อย้ายหมุด)")
    picked_key = f"picked_{key}"
    if picked_key not in st.session_state:
        st.session_state[picked_key] = {"lat": p.get("lat"), "lng": p.get("lng")}
    picked = st.session_state[picked_key]

    if HAS_MAP:
        m = map_view.pick_location_map(db.get_boundaries(), picked["lat"], picked["lng"])
        result = st_folium(m, height=380, width=None,
                           returned_objects=["last_clicked"], key=f"map_{key}")
        if result and result.get("last_clicked"):
            picked["lat"] = round(result["last_clicked"]["lat"], 6)
            picked["lng"] = round(result["last_clicked"]["lng"], 6)
            st.session_state[picked_key] = picked
        c_show, c_clear = st.columns([3, 1])
        with c_show:
            if picked["lat"] is not None:
                st.success(f"พิกัดที่ปัก: {picked['lat']:.6f}, {picked['lng']:.6f}")
            else:
                st.info("ยังไม่ได้ปักหมุด — คลิกในแผนที่ด้านบน")
        with c_clear:
            if st.button("ล้างหมุด", key=f"clear_{key}", use_container_width=True):
                st.session_state[picked_key] = {"lat": None, "lng": None}
                st.rerun()
    else:
        st.warning("แผนที่ไม่พร้อม — จะใช้พิกัดศูนย์กลาง สน.ลุมพินีชั่วคราว")

    section_title("📝 ข้อมูลคดี")
    with st.form(key, clear_on_submit=(prefill is None)):
        c1, c2, c3 = st.columns(3)
        case_number = c1.text_input("เลขคดี / เลขรับแจ้ง *", value=p.get("case_number", ""))
        station_label = c2.selectbox("สถานีที่รับแจ้ง *", st_labels, index=st_idx)
        report_date = c3.date_input("วันที่รับแจ้ง *", value=init_date)

        c4, c5 = st.columns([1, 1])
        crime_type_sel = c4.selectbox("ประเภทคดี *", types, index=type_idx)
        crime_custom = c5.text_input("ถ้าเลือก 'อื่น ๆ' ให้ระบุที่นี่",
                                     value=cur_type if cur_type not in types else "")

        # พื้นที่/ย่าน: เลือกจากรายการมาตรฐาน (แก้ปัญหาพิมพ์ชื่อย่านไม่ตรงกัน)
        nb_list = db.get_neighborhoods()
        area_options = nb_list + [OTHER]
        cur_area = (p.get("area") or "").strip()
        area_idx = nb_list.index(cur_area) if cur_area in nb_list else (
            len(area_options) - 1 if cur_area else 0)
        c6, c6b, c7 = st.columns(3)
        area_sel = c6.selectbox("พื้นที่/ย่าน", area_options, index=area_idx)
        area_custom = c6b.text_input("ถ้าเลือก 'อื่น ๆ' ระบุย่านที่นี่",
                                     value=cur_area if cur_area not in nb_list else "")
        location_detail = c7.text_input("จุดเกิดเหตุ (ถนน/ซอย)", value=p.get("location_detail", "") or "")

        victim_name = damage = time_bucket = weapon = severity = ""
        if category == CAT_ONLINE:
            c10, c11 = st.columns(2)
            victim_name = c10.text_input("ชื่อผู้เสียหาย", value=p.get("victim_name", "") or "")
            damage = c11.number_input("มูลค่าความเสียหาย (บาท)", min_value=0.0, step=1000.0,
                                      value=float(p.get("damage_amount", 0) or 0))
        else:
            c10, c11, c12 = st.columns(3)
            tb = p.get("time_bucket") if p.get("time_bucket") in TIME_BUCKETS else "ไม่ระบุ"
            time_bucket = c10.selectbox("ช่วงเวลาเกิดเหตุ", TIME_BUCKETS, index=TIME_BUCKETS.index(tb))
            weapon = c11.text_input("อาวุธที่ใช้", value=p.get("weapon", "") or "")
            severity = c12.selectbox("ระดับความรุนแรง (1=น้อย 3=มาก)", [1, 2, 3],
                                     index=int(p.get("severity", 1) or 1) - 1)

        mo = st.text_area("รายละเอียด / อุบาย / พฤติการณ์", value=p.get("mo_description", "") or "", height=70)
        st.markdown("**จุดร่วม (Indicators) — บรรทัดละ 1 ค่า**")
        hint("จุดร่วมคือข้อมูลที่ใช้เชื่อมโยงคดี เช่นเลขบัญชีหรือทะเบียนรถเดียวกันในหลายคดี")
        ind_types = db.CYBER_INDICATORS if category == CAT_ONLINE else db.PHYSICAL_INDICATORS
        ind_inputs = {}
        cols = st.columns(2)
        for i, t in enumerate(ind_types):
            ind_inputs[t] = cols[i % 2].text_area(db.INDICATOR_LABELS[t], value=ind.get(t, ""),
                                                  height=68, key=f"{key}_{t}")
        submitted = st.form_submit_button(submit_label, use_container_width=True)

    crime_type = crime_custom.strip() if (crime_type_sel == OTHER and crime_custom.strip()) else crime_type_sel
    # ประกอบค่า area: เลือกจากรายการ หรือค่าที่ระบุเองในช่อง 'อื่น ๆ'
    # (คดีเก่าที่ค่าไม่อยู่ในรายการ จะถูกเติมในช่องระบุเองให้อัตโนมัติ — ค่าเดิมไม่หาย)
    if area_sel == OTHER:
        area_val = area_custom.strip() if area_custom.strip() else cur_area
    else:
        area_val = area_sel
    indicators = []
    for t, txt in ind_inputs.items():
        for v in parse_lines(txt):
            indicators.append((t, v))
    picked = st.session_state.get(picked_key, {})
    lat = picked.get("lat") if picked.get("lat") is not None else LUMP[0]
    lng = picked.get("lng") if picked.get("lng") is not None else LUMP[1]
    data = dict(category=category, case_number=case_number.strip(),
                station_id=dict(zip(st_labels, st_ids))[station_label],
                crime_type=crime_type, report_date=str(report_date),
                time_bucket=time_bucket or "", area=area_val.strip(),
                location_detail=location_detail.strip(), lat=lat, lng=lng,
                victim_name=(victim_name or "").strip(), damage_amount=float(damage or 0),
                weapon=(weapon or "").strip(), severity=int(severity or 1),
                mo_description=mo.strip(), indicators=indicators)
    return data, submitted, picked_key


# ================================================================
# หน้าต่าง ๆ
# ================================================================
def page_dashboard():
    section_title("📊 ภาพรวมระบบ")
    s = db.get_dashboard_stats()
    c = st.columns(4)
    c[0].markdown(metric_card("คดีออนไลน์", f'{s["cyber_cases"]:,}'), unsafe_allow_html=True)
    c[1].markdown(metric_card("คดีในพื้นที่", f'{s["physical_cases"]:,}', "signal"), unsafe_allow_html=True)
    c[2].markdown(metric_card("ความเสียหายออนไลน์ (บาท)", f'{s["total_damage"]:,.0f}', "gold"), unsafe_allow_html=True)
    c[3].markdown(metric_card("คู่คดีเชื่อมโยง (ออนไลน์/พื้นที่)",
                              f'{s["cyber_links"]} / {s["physical_links"]}', "green"), unsafe_allow_html=True)
    st.write("")
    sc1, sc2, _ = st.columns([1, 1, 3])
    if sc1.button("➕ บันทึกคดีออนไลน์", use_container_width=True):
        st.session_state.page = "บันทึกคดีออนไลน์"; st.rerun()
    if sc2.button("🚓 บันทึกคดีในพื้นที่", use_container_width=True):
        st.session_state.page = "บันทึกคดีในพื้นที่"; st.rerun()

    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        section_title("🚩 จุดร่วมคดีออนไลน์ที่ถูกใช้ซ้ำ")
        top = db.get_top_reused_indicators(CAT_ONLINE)
        if top:
            st.dataframe(pd.DataFrame([{"ชนิด": db.INDICATOR_LABELS.get(t["indicator_type"]),
                                        "ค่า": t["raw_value"], "พบใน(คดี)": t["used"]} for t in top]),
                         use_container_width=True, hide_index=True)
        else:
            st.info("ยังไม่มี")
    with col2:
        section_title("🚓 จุดร่วมคดีในพื้นที่ที่ถูกใช้ซ้ำ")
        top = db.get_top_reused_indicators(CAT_PHYSICAL)
        if top:
            st.dataframe(pd.DataFrame([{"ชนิด": db.INDICATOR_LABELS.get(t["indicator_type"]),
                                        "ค่า": t["raw_value"], "พบใน(คดี)": t["used"]} for t in top]),
                         use_container_width=True, hide_index=True)
        else:
            st.info("ยังไม่มี")

    section_title("🗂️ คดีล่าสุด")
    cases = db.get_cases()
    if cases:
        df = pd.DataFrame([{"เลขคดี": c["case_number"], "กลุ่ม": category_label(c["category"]),
                            "สถานี": c["station_code"], "วันที่": c["report_date"],
                            "ประเภท": c["crime_type"], "พื้นที่": c["area"]} for c in cases])
        st.dataframe(df, use_container_width=True, hide_index=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="คดี")
        st.download_button("⬇️ ส่งออกเป็น Excel", buf.getvalue(),
                           file_name="cases.xlsx", use_container_width=True)
    else:
        st.info("ยังไม่มีคดีในระบบ — เริ่มบันทึกได้เลย หรือให้ผู้ดูแลกดโหลดข้อมูลตัวอย่าง")


def page_new_online():
    section_title("💻 บันทึกคดีออนไลน์")
    hint("คดีออนไลน์: หลอกลงทุน แก๊งคอลเซ็นเตอร์ หลอกซื้อขาย Romance Scam ฯลฯ")
    _new_case(CAT_ONLINE, "new_online")


def page_new_physical():
    section_title("🚓 บันทึกคดีในพื้นที่")
    hint("คดีในพื้นที่: ลักทรัพย์ วิ่งราวทรัพย์ ชิงทรัพย์ ปล้นทรัพย์ ก่อจลาจล ฯลฯ")
    _new_case(CAT_PHYSICAL, "new_physical")


def _new_case(category, key):
    data, submitted, picked_key = case_form(category, key=key, submit_label="💾 บันทึกและตรวจการเชื่อมโยง")
    if submitted:
        if not data["case_number"]:
            st.error("กรุณากรอกเลขคดี"); return
        u = current_user()
        cid = db.add_case(created_by=u["id"] if u else None, **data)
        st.success(f"บันทึกคดี {data['case_number']} เรียบร้อย")
        st.session_state.pop(picked_key, None)
        links = db.detect_links(cid)
        if links:
            st.markdown(f'<div class="link-alert"><h3>⚠️ พบความเชื่อมโยง {len(links)} คดี</h3>'
                        '<p>ควรประสานหน่วยที่เกี่ยวข้อง</p></div>', unsafe_allow_html=True)
            render_links(links)
        else:
            st.info("ยังไม่พบคดีอื่นที่ใช้จุดร่วมเดียวกัน")


def page_manage_cases():
    section_title("✏️ จัดการ / แก้ไขคดี")
    cases = db.get_cases()
    if not cases:
        st.info("ยังไม่มีคดี"); return
    lab = {f'[{category_label(c["category"])}] {c["case_number"]} — {c["station_code"]} ({c["crime_type"]})': c["case_id"]
           for c in cases}
    chosen = st.selectbox("เลือกคดี", list(lab.keys()))
    cid = lab[chosen]
    case = db.get_case(cid)
    prefill = dict(case); prefill["indicators"] = db.get_indicators_grouped(cid)
    data, submitted, picked_key = case_form(case["category"], prefill=prefill,
                                            key=f"edit_{cid}", submit_label="💾 บันทึกการแก้ไข")
    if submitted:
        if not data["case_number"]:
            st.error("กรุณากรอกเลขคดี"); return
        db.update_case(cid, **data)
        st.success("บันทึกการแก้ไขเรียบร้อย")
        links = db.detect_links(cid)
        if links:
            render_links(links)

    st.divider()
    if is_admin():
        section_title("🗑️ ลบคดี (เฉพาะผู้ดูแล)")
        if st.checkbox("ยืนยันว่าต้องการลบคดีนี้"):
            if st.button("ลบคดีนี้", type="primary"):
                db.delete_case(cid); st.session_state.pop(picked_key, None)
                st.success("ลบแล้ว"); st.rerun()
    else:
        st.caption("การลบคดีทำได้เฉพาะผู้ดูแลระบบ")


def page_online_map():
    section_title("🌐 แผนผังคดีออนไลน์ — สำหรับมวลชนสัมพันธ์")
    hint("จุดน้ำเงิน = คดีออนไลน์ · ใช้ดูว่าควรไปเตือนภัย/ให้ความรู้ประชาชนที่พื้นที่ใด "
         "(ดูเส้นเชื่อมโยงคดีได้ที่เมนู 'แผนที่เชื่อมโยงคดี')")
    cases = db.get_cases(CAT_ONLINE)
    if HAS_MAP:
        # ส่ง pairs=[] เพื่อไม่วาดเส้นเชื่อม — เส้นเชื่อมย้ายไปหน้าแผนที่เชื่อมโยงคดี
        m = map_view.build_cyber_map(db.get_stations(), cases, [], db.get_boundaries())
        st_folium(m, width=None, height=520, returned_objects=[])
    else:
        st.warning("ยังไม่ได้ติดตั้งแผนที่")
    st.divider()
    section_title("ระดับความเสี่ยงรายย่าน (คดีออนไลน์)")
    hint("เกณฑ์: ≤3 คดี = ต่ำ · 4-5 คดี = ปานกลาง · >5 คดี = สูง")
    for d in db.risk_by_area(CAT_ONLINE):
        c1, c2, c3 = st.columns([2, 1, 1.3])
        c1.write(d["area"]); c2.write(f'{d["case_count"]} คดี')
        c3.markdown(risk_badge(d["risk_level"]), unsafe_allow_html=True)


def page_patrol_map():
    section_title("🚔 แผนผังสายตรวจ — คดีในพื้นที่")
    hint("วงสี = พื้นที่เสี่ยงจับกลุ่มอัตโนมัติจากจุดเกิดเหตุจริง "
         "(เขียว ≤3 · เหลือง 4-5 · แดง >5 คดี) · จุดแดงเล็ก = คดี · "
         "หมุดสามเหลี่ยม = จุดเสี่ยงที่เจ้าหน้าที่บันทึกเอง · ไม่มีเส้นเชื่อมในหน้านี้")
    cases = db.get_cases(CAT_PHYSICAL)

    c1, c2 = st.columns([1, 1.2])
    tb = c1.selectbox("กรองตามช่วงเวลาเกิดเหตุ (ช่วยจัดผลัดสายตรวจ)",
                      ["ทั้งหมด"] + TIME_BUCKETS)
    radius = c2.slider("รัศมีจับกลุ่มพื้นที่เสี่ยง (เมตร)", 200, 1000, 400, step=50)

    if tb != "ทั้งหมด":
        cases = [c for c in cases if c.get("time_bucket") == tb]

    # จับกลุ่มจากคดีที่ผ่านตัวกรองแล้ว — ตัวกรองเวลาจึงมีผลกับวงสีด้วย
    clusters = map_view.cluster_cases(cases, radius)

    if HAS_MAP:
        m = map_view.build_patrol_map(db.get_stations(), cases, clusters,
                                      db.get_risk_points(CAT_PHYSICAL),
                                      db.get_boundaries())
        st_folium(m, width=None, height=520, returned_objects=[])
    else:
        st.warning("ยังไม่ได้ติดตั้งแผนที่")

    st.divider()
    section_title(f"สรุปกลุ่มพื้นที่เสี่ยง (รัศมี {radius} ม.)")
    if clusters:
        for cl in clusters:
            lv = map_view.cluster_level(cl["count"])
            nums = ", ".join(c["case_number"] for c in cl["cases"][:6])
            more = "" if cl["count"] <= 6 else f" +{cl['count']-6}"
            cA, cB, cC = st.columns([1, 3, 1.3])
            cA.write(f'{cl["count"]} คดี')
            cB.write(f'{nums}{more}')
            cC.markdown(risk_badge(lv), unsafe_allow_html=True)
    else:
        st.info("ยังไม่มีคดีที่มีพิกัดในช่วงเวลาที่เลือก")

    st.divider()
    section_title("ระดับความเสี่ยงรายย่าน (จากชื่อย่านที่บันทึก)")
    hint("เกณฑ์: ≤3 คดี = ต่ำ · 4-5 คดี = ปานกลาง · >5 คดี = สูง")
    for d in db.risk_by_area(CAT_PHYSICAL):
        c1, c2, c3 = st.columns([2, 1, 1.3])
        c1.write(d["area"]); c2.write(f'{d["case_count"]} คดี')
        c3.markdown(risk_badge(d["risk_level"]), unsafe_allow_html=True)


def page_linkage_map():
    section_title("🔗 แผนที่เชื่อมโยงคดี")
    hint("เส้นส้ม = คดีที่ใช้จุดร่วมเดียวกัน (บัญชี/ไลน์/เบอร์/ทะเบียนรถ/ลักษณะคนร้าย) · "
         "เส้นหนา = จุดร่วมตรงกันหลายรายการ · หน้านี้ไม่แสดงวงพื้นที่เสี่ยงเพื่อไม่ให้ตาลาย")
    grp = st.radio("เลือกกลุ่มคดี", ["คดีออนไลน์", "คดีในพื้นที่"], horizontal=True)
    cat = CAT_ONLINE if grp == "คดีออนไลน์" else CAT_PHYSICAL
    dot = "#25406B" if cat == CAT_ONLINE else "#B3434F"

    cases = db.get_cases(cat)
    pairs = db.get_all_link_pairs(cat)

    if HAS_MAP:
        m = map_view.build_linkage_map(db.get_stations(), cases, pairs,
                                       db.get_boundaries(), dot_color=dot)
        st_folium(m, width=None, height=520, returned_objects=[])
    else:
        st.warning("ยังไม่ได้ติดตั้งแผนที่")

    st.divider()
    section_title("รายการคู่คดีที่เชื่อมโยง")
    byid = {c["case_id"]: c for c in cases}
    if pairs:
        for a, b, n in pairs:
            if a in byid and b in byid:
                st.markdown(f'🔗 **{byid[a]["case_number"]}** ({byid[a]["station_code"]}) — '
                            f'**{byid[b]["case_number"]}** ({byid[b]["station_code"]}) · {n} จุดร่วม')
    else:
        st.info("ยังไม่มีคู่คดีที่เชื่อมโยงในกลุ่มนี้")


def page_manage_area():
    section_title("🗺️ จัดการพื้นที่ / จุดเสี่ยง (เฉพาะผู้ดูแล)")
    t1, t2, t3 = st.tabs(["สถานี & ทิศ & พิกัด", "จุดเสี่ยง", "ขอบเขตแผนที่ (KML)"])
    with t1:
        hint("แก้ชื่อ/ทิศ/พิกัด เพิ่ม/ลบแถวได้ แล้วกดบันทึก")
        rows = db.get_stations()
        df = pd.DataFrame(rows)[["code", "name", "direction", "lat", "lng", "is_main"]] if rows \
            else pd.DataFrame(columns=["code", "name", "direction", "lat", "lng", "is_main"])
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                column_config={"code": "รหัส สน.", "name": "ชื่อ",
                                    "direction": st.column_config.SelectboxColumn("ทิศ", options=DIRECTIONS),
                                    "is_main": st.column_config.CheckboxColumn("สน.หลัก")})
        if st.button("💾 บันทึกสถานี"):
            db.save_stations(edited.to_dict("records")); st.success("บันทึกแล้ว"); st.rerun()
    with t2:
        cat_label = st.radio("กลุ่ม", ["คดีในพื้นที่", "ออนไลน์"], horizontal=True, key="rp_cat")
        cat = CAT_PHYSICAL if cat_label == "คดีในพื้นที่" else CAT_ONLINE
        pts = db.get_risk_points(cat)
        df = pd.DataFrame(pts)[["name", "lat", "lng", "level", "note"]] if pts else \
            pd.DataFrame(columns=["name", "lat", "lng", "level", "note"])
        hint("เพิ่ม/แก้/ย้าย(แก้พิกัด)/ลบจุดเสี่ยง แล้วกดบันทึก")
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                column_config={"name": "ชื่อจุด",
                                    "level": st.column_config.SelectboxColumn("ระดับเสี่ยง", options=RISK_LEVELS),
                                    "note": "หมายเหตุ"})
        if st.button("💾 บันทึกจุดเสี่ยง"):
            db.save_risk_points(cat, edited.to_dict("records")); st.success("บันทึกแล้ว"); st.rerun()
    with t3:
        hint("นำเข้าไฟล์ขอบเขตจาก Google My Maps (รองรับหลาย สน. ในไฟล์เดียว)")
        up = st.file_uploader("อัปโหลดไฟล์ขอบเขต", type=["kml", "kmz", "geojson", "json"])
        if up is not None:
            try:
                named = geo.parse_named_boundaries(up.name, up.getvalue())
                if named:
                    areas = []
                    for a in named:
                        nm = a["name"] or ""
                        code = nm if nm and nm != "Polygon 1" else "สน.ลุมพินี"
                        areas.append({"code": code, "name": nm,
                                      "is_main": 1 if ("ลุมพินี" in code or nm == "Polygon 1") else 0,
                                      "polygon": a["polygon"]})
                    db.set_boundaries(areas)
                    st.success(f"นำเข้าขอบเขต {len(areas)} พื้นที่เรียบร้อย")
                else:
                    st.error("อ่านขอบเขตไม่ได้")
            except Exception as e:
                st.error(f"นำเข้าไม่สำเร็จ: {e}")
        cur = db.get_boundaries()
        if cur:
            st.dataframe(pd.DataFrame([{"พื้นที่": b.get("code", ""),
                                        "สน.หลัก": "✓" if b.get("is_main") else "",
                                        "จำนวนจุด": len(b.get("polygon", []))} for b in cur]),
                         use_container_width=True, hide_index=True)


def page_search():
    section_title("🔍 ค้นหาจุดร่วม")
    hint("ค้นว่าเลขบัญชี/ไลน์/เบอร์/ทะเบียนรถ ปรากฏในคดีใดบ้าง")
    types = list(db.INDICATOR_LABELS.keys())
    c1, c2 = st.columns([1, 2])
    t = c1.selectbox("ชนิด", types, format_func=lambda k: db.INDICATOR_LABELS[k])
    kw = c2.text_input("ค่าที่ค้นหา")
    if st.button("ค้นหา") and kw.strip():
        norm = db.normalize_value(t, kw)
        all_inds = db._all_indicators()
        cases = {c["case_id"]: c for c in db.get_cases()}
        rows = [cases[i["case_id"]] for i in all_inds
                if i["indicator_type"] == t and i["norm_value"] == norm and i["case_id"] in cases]
        if rows:
            st.success(f"พบ {len(rows)} คดี")
            st.dataframe(pd.DataFrame([{"เลขคดี": r["case_number"],
                                        "กลุ่ม": category_label(r["category"]),
                                        "สถานี": r["station_code"], "ประเภท": r["crime_type"]} for r in rows]),
                         use_container_width=True, hide_index=True)
            if len(rows) > 1:
                st.warning("⚠️ จุดร่วมนี้ปรากฏหลายคดี — อาจเป็นคนร้ายรายเดียวกัน")
        else:
            st.info("ไม่พบ")


def page_guide():
    section_title("📖 คู่มือการใช้งาน CyberLink")
    st.markdown("""
    <div class="guide-card"><h3>1) ระบบนี้ใช้ทำอะไร</h3>
      <p><b>ปัญหา:</b> คนร้ายก่อเหตุข้ามพื้นที่ แต่ข้อมูลแต่ละ สน. แยกกัน มองไม่เห็นความเชื่อมโยง</p>
      <p><b>ระบบช่วย:</b> บันทึก "จุดร่วม" (บัญชี ไลน์ เบอร์ ทะเบียนรถ) พอบันทึกคดีใหม่ ระบบวนตรวจอัตโนมัติ
      ว่าจุดร่วมเคยปรากฏในคดีอื่นไหม ถ้าพบ = เชื่อมโยงคดีให้ทันที</p></div>
    <div class="guide-card"><h3>2) ข้อมูล 2 กลุ่ม</h3>
      <p><b>คดีออนไลน์</b> — ใช้บัญชี/ไลน์/เบอร์/URL เชื่อม → ทำ <b>มวลชนสัมพันธ์</b></p>
      <p><b>คดีในพื้นที่</b> — ใช้ทะเบียนรถ/ลักษณะคนร้าย เชื่อม → <b>บริหารสายตรวจ</b></p></div>
    <div class="guide-card"><h3>3) ขั้นตอนบันทึกคดี</h3>
      <p><span class="guide-step">1</span>เลือกเมนู บันทึกคดีออนไลน์ หรือ ในพื้นที่</p>
      <p><span class="guide-step">2</span>ปักหมุดจุดเกิดเหตุบนแผนที่ (ไม่ต้องจำพิกัด)</p>
      <p><span class="guide-step">3</span>กรอกข้อมูลคดี</p>
      <p><span class="guide-step">4</span>กรอกจุดร่วม บรรทัดละ 1 ค่า</p>
      <p><span class="guide-step">5</span>กดบันทึก ระบบแจ้งทันทีถ้าพบการเชื่อมโยง</p></div>
    <div class="guide-card"><h3>4) การเชื่อมโยงทำงานยังไง</h3>
      <p>ระบบจัดรูปแบบข้อมูลให้เหมือนกันก่อน (เช่นตัดขีดออกจากเลขบัญชี) แล้วเทียบ</p>
      <p><b>ตัวอย่าง:</b> <code>888-1-11222-3</code> กับ <code>8881112223</code> = บัญชีเดียวกัน → เชื่อมโยง</p></div>
    <div class="guide-card"><h3>5) การอ่านแผนที่</h3>
      <p>สีขอบเขต = แต่ละ สน. · วงกลม <span style="color:#FF9C97">แดง=เสี่ยงสูง</span>
      <span style="color:#FFD37A">ส้ม=กลาง</span> <span style="color:#8FD5AB">เขียว=ต่ำ</span></p>
      <p>เส้นสีส้ม = คดีที่เชื่อมโยงกัน</p></div>
    <div class="guide-card"><h3>6) คำถามที่พบบ่อย</h3>
      <p><b>ไม่รู้พิกัด?</b> คลิกในแผนที่ ระบบกรอกให้เอง</p>
      <p><b>สมัครไม่ได้?</b> ต้องมีรหัสเชิญจากผู้ดูแล และระบบจำกัด 20 บัญชี</p>
      <p><b>ลบคดีไม่ได้?</b> การลบทำได้เฉพาะผู้ดูแลระบบ</p>
      <p><b>ข้อมูลเห็นตรงกันทุกเครื่องไหม?</b> ใช่ ข้อมูลอยู่บนเซิร์ฟเวอร์กลาง (Supabase)</p></div>
    """, unsafe_allow_html=True)


def page_admin():
    section_title("🛠️ ผู้ดูแลระบบ")
    tab_inv, tab_usr, tab_nb, tab_data = st.tabs(["รหัสเชิญ", "ผู้ใช้", "ย่าน/พื้นที่", "ข้อมูลระบบ"])
    u = current_user()

    with tab_inv:
        st.caption(f"จำนวนผู้ใช้ปัจจุบัน {auth.user_count()} / {auth.MAX_USERS} บัญชี")
        if st.button("➕ สร้างรหัสเชิญใหม่"):
            res = auth.create_invite(u["id"])
            if res["ok"]:
                st.success(f"รหัสเชิญใหม่: {res['code']} (ส่งให้ผู้ที่จะสมัคร)")
            else:
                st.error(res["error"])
        invs = auth.list_invites()
        if invs:
            df = pd.DataFrame([{"รหัส": i["code"],
                                "สถานะ": "ใช้แล้ว" if i.get("used_by") else "ยังไม่ใช้",
                                "สร้างเมื่อ": (i.get("created_at") or "")[:10]} for i in invs])
            st.dataframe(df, use_container_width=True, hide_index=True)
            unused = [i["code"] for i in invs if not i.get("used_by")]
            if unused:
                rc = st.selectbox("ยกเลิกรหัสที่ยังไม่ถูกใช้", unused)
                if st.button("ยกเลิกรหัสนี้"):
                    auth.revoke_invite(rc); st.success("ยกเลิกแล้ว"); st.rerun()

    with tab_usr:
        users = auth.list_users()
        if users:
            st.dataframe(pd.DataFrame([{"อีเมล": x["email"], "บทบาท": x["role"],
                                        "สร้างเมื่อ": (x.get("created_at") or "")[:10]} for x in users]),
                         use_container_width=True, hide_index=True)
            emails = {x["email"]: x for x in users}
            sel = st.selectbox("เลือกผู้ใช้", list(emails.keys()))
            target = emails[sel]
            col1, col2 = st.columns(2)
            with col1:
                new_role = st.selectbox("เปลี่ยนบทบาท", ["user", "admin"],
                                        index=0 if target["role"] == "user" else 1)
                if st.button("บันทึกบทบาท"):
                    auth.set_role(target["id"], new_role); st.success("อัปเดตแล้ว"); st.rerun()
            with col2:
                if target["id"] != u["id"]:
                    if st.checkbox(f"ยืนยันลบผู้ใช้ {sel}"):
                        if st.button("ลบผู้ใช้นี้", type="primary"):
                            auth.delete_user(target["id"]); st.success("ลบแล้ว"); st.rerun()
                else:
                    st.caption("ลบบัญชีตัวเองไม่ได้")

    with tab_nb:
        st.caption("รายการย่านมาตรฐานที่แสดงใน dropdown ตอนบันทึกคดี — เพิ่ม/แก้/ลบได้ แล้วกดบันทึก "
                   "(ช่วยแก้ปัญหาเจ้าหน้าที่พิมพ์ชื่อย่านไม่ตรงกัน)")
        nb = db.get_neighborhoods()
        nb_df = pd.DataFrame({"ชื่อย่าน": nb})
        edited_nb = st.data_editor(nb_df, num_rows="dynamic", use_container_width=True,
                                   key="nb_editor")
        if st.button("💾 บันทึกรายการย่าน"):
            items = [str(x).strip() for x in edited_nb["ชื่อย่าน"].tolist() if str(x).strip()]
            db.save_neighborhoods(items)
            st.success("บันทึกรายการย่านแล้ว"); st.rerun()
        st.caption("หมายเหตุ: การแก้ไขรายการนี้ไม่กระทบข้อมูลย่านที่บันทึกในคดีเดิม")

    with tab_data:
        st.caption("จัดการชุดข้อมูลตัวอย่างสำหรับการนำเสนอ")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📦 โหลดข้อมูลตัวอย่าง"):
                seed_data.load_demo(); st.success("โหลดข้อมูลตัวอย่างแล้ว"); st.rerun()
        with col2:
            if st.checkbox("⚠️ ยืนยันล้างข้อมูลคดีทั้งหมด"):
                if st.button("ล้างข้อมูลคดี + จุดเสี่ยง", type="primary"):
                    seed_data.clear_data(); st.success("ล้างแล้ว (เก็บผู้ใช้/สถานี/ขอบเขตไว้)"); st.rerun()


# ================================================================
# Main
# ================================================================
def main():
    # 1) เช็กว่าตั้งค่า Supabase ครบไหม
    if not supa.is_configured():
        st.error("ยังไม่ได้ตั้งค่าการเชื่อมต่อ Supabase")
        st.markdown("ต้องใส่ค่า `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` "
                    "ในไฟล์ `.streamlit/secrets.toml` (รันในเครื่อง) หรือในเมนู Secrets (บน Streamlit Cloud)")
        st.stop()

    # 2) ยังไม่ล็อกอิน -> หน้าล็อกอิน
    if not current_user():
        login_screen()
        st.stop()

    # 3) สร้างโครงพื้นฐานครั้งแรก (สถานี+ขอบเขต) — ครั้งเดียวต่อ session
    if not st.session_state.get("_base_ready"):
        try:
            seed_data.ensure_base_data()
        except Exception as e:
            st.warning(f"เตรียมข้อมูลพื้นฐานไม่สำเร็จ: {e}")
        st.session_state["_base_ready"] = True

    u = current_user()
    role_badge = f'<span class="badge {"admin" if u["role"]=="admin" else "user"}">{u["role"]}</span>'
    st.markdown(f"""<div class="esri-topbar"><div class="logo">{SHIELD}</div>
      <div><div class="title">CyberLink · ระบบคดีและพื้นที่เสี่ยง</div>
      <div class="sub">สน.ลุมพินี และเขตติดต่อ</div></div>
      <div class="who">{u['email']} {role_badge}</div></div>""", unsafe_allow_html=True)

    # เมนูตามบทบาท
    pages = {
        "แดชบอร์ด": ("📊 แดชบอร์ด", page_dashboard),
        "คู่มือ": ("📖 คู่มือการใช้งาน", page_guide),
        "บันทึกคดีออนไลน์": ("💻 บันทึกคดีออนไลน์", page_new_online),
        "บันทึกคดีในพื้นที่": ("🚓 บันทึกคดีในพื้นที่", page_new_physical),
        "จัดการคดี": ("✏️ จัดการ/แก้ไขคดี", page_manage_cases),
        "แผนผังออนไลน์": ("🌐 แผนผังคดีออนไลน์", page_online_map),
        "แผนผังสายตรวจ": ("🚔 แผนผังสายตรวจ", page_patrol_map),
        "แผนที่เชื่อมโยง": ("🔗 แผนที่เชื่อมโยงคดี", page_linkage_map),
        "ค้นหา": ("🔍 ค้นหาจุดร่วม", page_search),
    }
    if is_admin():
        pages["จัดการพื้นที่"] = ("🗺️ จัดการพื้นที่/จุดเสี่ยง", page_manage_area)
        pages["ผู้ดูแลระบบ"] = ("🛠️ ผู้ดูแลระบบ", page_admin)

    if "page" not in st.session_state or st.session_state.page not in pages:
        st.session_state.page = "แดชบอร์ด"

    with st.sidebar:
        st.markdown("### เมนูหลัก")
        keys = list(pages.keys())
        labels = [pages[k][0] for k in keys]
        cur_idx = keys.index(st.session_state.page)
        sel = st.radio("ไปยังหน้า", labels, index=cur_idx, label_visibility="collapsed")
        st.session_state.page = keys[labels.index(sel)]
        st.divider()
        st.caption(f"เข้าใช้งานโดย: {u['email']}")
        if st.button("ออกจากระบบ", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    pages[st.session_state.page][1]()


main()
