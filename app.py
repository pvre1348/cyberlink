"""
app.py — ระบบบริหารข้อมูลคดีและพื้นที่เสี่ยง (อิงพื้นที่ สน.ลุมพินี)
สร้างด้วย Streamlit + folium

หน้าจอ:
  แดชบอร์ด · บันทึกคดี · จัดการ/แก้ไขคดี ·
  แผนผังไซเบอร์ (มวลชนสัมพันธ์) · แผนผังสายตรวจ (คดีพื้นที่) ·
  จัดการพื้นที่/จุดเสี่ยง · ค้นหา
รัน:  python -m streamlit run app.py
"""
import os
import io
from datetime import date

import pandas as pd
import streamlit as st

import database as db
import seed_data
import geo
import map_view

# โหลดแผนที่ (ถ้ายังไม่ได้ลงไลบรารีจะแจ้งเตือนแทนที่จะพัง)
try:
    import folium  # noqa
    from streamlit_folium import st_folium
    HAS_MAP = True
except Exception:
    HAS_MAP = False

st.set_page_config(page_title="ระบบคดีและพื้นที่เสี่ยง", page_icon="🛡️", layout="wide")

if not os.path.exists(db.DB_PATH):
    seed_data.reset_and_seed()
else:
    db.init_db()

# ---------------------------------------------------------------- ค่าคงที่
CYBER_TYPES = ["หลอกลงทุน", "แก๊งคอลเซ็นเตอร์", "หลอกซื้อขายออนไลน์",
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

# ---------------------------------------------------------------- ธีม
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Prompt:wght@400;500;600;700&family=IBM+Plex+Sans+Thai:wght@300;400;500;600&display=swap');
:root{--ink:#14233D;--ink2:#1E3357;--signal:#E0533D;--gold:#C9A227;--bg:#F6F8FB;--line:#E4E9F1;--muted:#6B7A90;}
html,body,[class*="css"]{font-family:'IBM Plex Sans Thai',sans-serif;}
h1,h2,h3,h4,h5{font-family:'Prompt',sans-serif;color:var(--ink);}
.stApp{background:var(--bg);}
.block-container{padding-top:1.3rem;padding-bottom:3rem;max-width:1320px;}
.portal{background:linear-gradient(110deg,var(--ink) 0%,var(--ink2) 100%);color:#fff;
  padding:16px 24px;border-radius:14px;margin-bottom:18px;display:flex;align-items:center;gap:16px;
  border-bottom:4px solid var(--signal);}
.portal h1{color:#fff;margin:0;font-size:1.3rem;}
.portal p{margin:.2rem 0 0;opacity:.8;font-size:.85rem;}
.metric-card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:15px 18px;
  position:relative;overflow:hidden;box-shadow:0 1px 2px rgba(20,35,61,.04);}
.metric-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--ink);}
.metric-card.signal:before{background:var(--signal);}
.metric-card.gold:before{background:var(--gold);}
.metric-card .label{font-size:.8rem;color:var(--muted);font-weight:500;}
.metric-card .value{font-size:1.7rem;font-weight:700;color:var(--ink);font-family:'Prompt';line-height:1.25;}
.section-title{font-family:'Prompt';font-weight:600;color:var(--ink);font-size:1.05rem;
  margin:8px 0 10px;padding-left:10px;border-left:3px solid var(--signal);}
.badge{padding:3px 14px;border-radius:20px;font-weight:600;font-size:.85rem;}
.badge.high{background:#FBE4E1;color:#C0271A;}.badge.mid{background:#FCF1DA;color:#9A6B00;}
.badge.low{background:#E2F2E9;color:#1F6B45;}
.link-alert{background:#FFF4F1;border:1px solid var(--signal);border-left:5px solid var(--signal);
  border-radius:12px;padding:14px 18px;margin:8px 0;}
.link-alert h3{color:var(--signal);margin:0 0 4px;font-size:1.05rem;}
.shared-chip{display:inline-block;background:var(--ink);color:#fff;padding:3px 10px;border-radius:6px;
  font-size:.8rem;margin:3px 5px 3px 0;}
.link-row{padding:9px 0;border-bottom:1px solid var(--line);}
section[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--line);}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

SHIELD = ('<svg width="40" height="40" viewBox="0 0 24 24" fill="none">'
          '<path d="M12 2L4 5v6c0 5 3.5 8.5 8 11 4.5-2.5 8-6 8-11V5l-8-3z" '
          'fill="#C9A227" stroke="#fff" stroke-width="1"/>'
          '<path d="M12 7v8M8 11h8" stroke="#14233D" stroke-width="1.6"/></svg>')

st.markdown(f"""<div class="portal"><div>{SHIELD}</div>
<div><h1>ระบบบริหารข้อมูลคดีและพื้นที่เสี่ยง</h1>
<p>เชื่อมโยงคดีข้ามพื้นที่ · บริหารงานสายตรวจ · มวลชนสัมพันธ์ — พื้นที่ สน.ลุมพินี และเขตติดต่อ</p>
</div></div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers
def metric_card(label, value, style=""):
    return f'<div class="metric-card {style}"><div class="label">{label}</div><div class="value">{value}</div></div>'


def section_title(t):
    st.markdown(f'<div class="section-title">{t}</div>', unsafe_allow_html=True)


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


def station_pickers(prefill):
    stations = db.get_stations()
    labels = [f'{s["code"]} — {s["name"]}' for s in stations]
    ids = [s["station_id"] for s in stations]
    idx = ids.index(prefill["station_id"]) if prefill.get("station_id") in ids else 0
    return stations, labels, ids, idx


# ---------------------------------------------------------------- ฟอร์มคดี
def case_form(category, prefill=None, key="form", submit_label="บันทึก"):
    p = prefill or {}
    stations, labels, ids, st_idx = station_pickers(p)
    types = CYBER_TYPES if category == "cyber" else PHYSICAL_TYPES
    cur_type = p.get("crime_type")
    type_idx = types.index(cur_type) if cur_type in types else 0
    init_date = date.fromisoformat(p["report_date"]) if p.get("report_date") else date.today()
    ind = p.get("indicators", {})
    def_lat = p.get("lat") if p.get("lat") is not None else LUMP[0]
    def_lng = p.get("lng") if p.get("lng") is not None else LUMP[1]

    with st.form(key, clear_on_submit=(prefill is None)):
        c1, c2, c3 = st.columns(3)
        case_number = c1.text_input("เลขคดี / เลขรับแจ้ง *", value=p.get("case_number", ""))
        station_label = c2.selectbox("สถานีที่รับแจ้ง *", labels, index=st_idx)
        report_date = c3.date_input("วันที่รับแจ้ง *", value=init_date)

        c4, c5 = st.columns([1, 1])
        crime_type_sel = c4.selectbox("ประเภทคดี *", types, index=type_idx)
        crime_custom = c5.text_input("ถ้าเลือก 'อื่น ๆ' ระบุที่นี่",
                                     value=cur_type if cur_type not in types else "")

        c6, c7 = st.columns(2)
        area = c6.text_input("พื้นที่ (ตำบล/เขต/ย่าน)", value=p.get("area", "") or "")
        location_detail = c7.text_input("จุดเกิดเหตุ (ถนน/ซอย)", value=p.get("location_detail", "") or "")

        # พิกัด (ใช้วางบนแผนที่) — หาพิกัดได้จากหน้า "จัดการพื้นที่"
        c8, c9 = st.columns(2)
        lat = c8.number_input("พิกัด lat", value=float(def_lat), format="%.6f")
        lng = c9.number_input("พิกัด lng", value=float(def_lng), format="%.6f")

        victim_name = damage = time_bucket = weapon = severity = ""
        if category == "cyber":
            c10, c11 = st.columns(2)
            victim_name = c10.text_input("ชื่อผู้เสียหาย", value=p.get("victim_name", "") or "")
            damage = c11.number_input("มูลค่าความเสียหาย (บาท)", min_value=0.0, step=1000.0,
                                      value=float(p.get("damage_amount", 0) or 0))
        else:
            c10, c11, c12 = st.columns(3)
            tb = p.get("time_bucket") if p.get("time_bucket") in TIME_BUCKETS else "ไม่ระบุ"
            time_bucket = c10.selectbox("ช่วงเวลาเกิดเหตุ", TIME_BUCKETS,
                                        index=TIME_BUCKETS.index(tb))
            weapon = c11.text_input("อาวุธที่ใช้", value=p.get("weapon", "") or "")
            severity = c12.selectbox("ระดับความรุนแรง (1=น้อย 3=มาก)", [1, 2, 3],
                                     index=int(p.get("severity", 1) or 1) - 1)

        mo = st.text_area("รายละเอียด / อุบาย / พฤติการณ์", value=p.get("mo_description", "") or "", height=70)

        st.markdown("**จุดร่วม (Indicators) — บรรทัดละ 1 ค่า**")
        ind_types = db.CYBER_INDICATORS if category == "cyber" else db.PHYSICAL_INDICATORS
        ind_inputs = {}
        cols = st.columns(2)
        for i, t in enumerate(ind_types):
            ind_inputs[t] = cols[i % 2].text_area(db.INDICATOR_LABELS[t],
                                                  value=ind.get(t, ""), height=68, key=f"{key}_{t}")
        submitted = st.form_submit_button(submit_label, use_container_width=True)

    # ประกอบข้อมูล
    crime_type = crime_custom.strip() if (crime_type_sel == OTHER and crime_custom.strip()) else crime_type_sel
    indicators = []
    for t, txt in ind_inputs.items():
        for v in parse_lines(txt):
            indicators.append((t, v))
    data = dict(
        category=category, case_number=case_number.strip(),
        station_id=dict(zip(labels, ids))[station_label],
        crime_type=crime_type, report_date=str(report_date),
        time_bucket=time_bucket or "", area=area.strip(),
        location_detail=location_detail.strip(), lat=lat, lng=lng,
        victim_name=(victim_name or "").strip(),
        damage_amount=float(damage or 0), weapon=(weapon or "").strip(),
        severity=int(severity or 1), mo_description=mo.strip(),
        indicators=indicators,
    )
    return data, submitted


# ---------------------------------------------------------------- หน้า: แดชบอร์ด
def page_dashboard():
    section_title("📊 ภาพรวมระบบ")
    s = db.get_dashboard_stats()
    c = st.columns(4)
    c[0].markdown(metric_card("คดีไซเบอร์", f'{s["cyber_cases"]:,}'), unsafe_allow_html=True)
    c[1].markdown(metric_card("คดีในพื้นที่", f'{s["physical_cases"]:,}', "signal"), unsafe_allow_html=True)
    c[2].markdown(metric_card("ความเสียหายไซเบอร์ (บาท)", f'{s["total_damage"]:,.0f}', "gold"), unsafe_allow_html=True)
    c[3].markdown(metric_card("คู่คดีเชื่อมโยง (ไซเบอร์/พื้นที่)",
                              f'{s["cyber_links"]} / {s["physical_links"]}'), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        section_title("🚩 จุดร่วมไซเบอร์ที่ถูกใช้ซ้ำ")
        top = db.get_top_reused_indicators("cyber")
        if top:
            st.dataframe(pd.DataFrame([{"ชนิด": db.INDICATOR_LABELS.get(t["indicator_type"]),
                                        "ค่า": t["raw_value"], "พบใน(คดี)": t["used"]} for t in top]),
                         use_container_width=True, hide_index=True)
        else:
            st.info("ยังไม่มี")
    with col2:
        section_title("🚓 จุดร่วมคดีพื้นที่ที่ถูกใช้ซ้ำ")
        top = db.get_top_reused_indicators("physical")
        if top:
            st.dataframe(pd.DataFrame([{"ชนิด": db.INDICATOR_LABELS.get(t["indicator_type"]),
                                        "ค่า": t["raw_value"], "พบใน(คดี)": t["used"]} for t in top]),
                         use_container_width=True, hide_index=True)
        else:
            st.info("ยังไม่มี")

    section_title("🗂️ คดีล่าสุด")
    cases = db.get_cases()
    if cases:
        df = pd.DataFrame([{"เลขคดี": c["case_number"], "กลุ่ม": "ไซเบอร์" if c["category"] == "cyber" else "พื้นที่",
                            "สถานี": c["station_code"], "วันที่": c["report_date"],
                            "ประเภท": c["crime_type"], "พื้นที่": c["area"]} for c in cases])
        st.dataframe(df, use_container_width=True, hide_index=True)
        # ส่งออก Excel
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="คดี")
        st.download_button("⬇️ ส่งออกเป็น Excel", buf.getvalue(),
                           file_name="cases.xlsx", use_container_width=True)


# ---------------------------------------------------------------- หน้า: บันทึกคดี
def page_new():
    section_title("📝 บันทึกคดีใหม่")
    cat_label = st.radio("เลือกกลุ่มคดี", ["ไซเบอร์", "คดีในพื้นที่"], horizontal=True)
    category = "cyber" if cat_label == "ไซเบอร์" else "physical"
    st.caption("กรอกข้อมูล + จุดร่วม เมื่อบันทึกระบบจะตรวจการเชื่อมโยงทันที (พิกัดหาได้จากหน้า 'จัดการพื้นที่')")

    data, submitted = case_form(category, key=f"new_{category}", submit_label="💾 บันทึกและตรวจการเชื่อมโยง")
    if submitted:
        if not data["case_number"]:
            st.error("กรุณากรอกเลขคดี"); return
        cid = db.add_case(**data)
        st.success(f"บันทึกคดี {data['case_number']} เรียบร้อย")
        links = db.detect_links(cid)
        if links:
            st.markdown(f'<div class="link-alert"><h3>⚠️ พบความเชื่อมโยง {len(links)} คดี</h3>'
                        '<p>ควรประสานหน่วยที่เกี่ยวข้อง</p></div>', unsafe_allow_html=True)
            render_links(links)
        else:
            st.info("ยังไม่พบคดีอื่นที่ใช้จุดร่วมเดียวกัน")


# ---------------------------------------------------------------- หน้า: จัดการ/แก้ไขคดี
def page_manage_cases():
    section_title("✏️ จัดการ / แก้ไขคดี")
    cases = db.get_cases()
    if not cases:
        st.info("ยังไม่มีคดี"); return
    lab = {f'[{"ไซ" if c["category"]=="cyber" else "พื้นที่"}] {c["case_number"]} — {c["station_code"]} ({c["crime_type"]})': c["case_id"]
           for c in cases}
    chosen = st.selectbox("เลือกคดี", list(lab.keys()))
    cid = lab[chosen]
    case = db.get_case(cid)
    prefill = dict(case); prefill["indicators"] = db.get_indicators_grouped(cid)

    data, submitted = case_form(case["category"], prefill=prefill, key=f"edit_{cid}",
                                submit_label="💾 บันทึกการแก้ไข")
    if submitted:
        if not data["case_number"]:
            st.error("กรุณากรอกเลขคดี"); return
        db.update_case(cid, **data)
        st.success("บันทึกการแก้ไขเรียบร้อย")
        links = db.detect_links(cid)
        if links:
            render_links(links)

    st.divider()
    section_title("🗑️ ลบคดี")
    if st.checkbox("ยืนยันว่าต้องการลบคดีนี้"):
        if st.button("ลบคดีนี้", type="primary"):
            db.delete_case(cid); st.success("ลบแล้ว"); st.rerun()


# ---------------------------------------------------------------- หน้า: แผนผังไซเบอร์
def page_cyber_map():
    section_title("🌐 แผนผังไซเบอร์ — สำหรับมวลชนสัมพันธ์")
    st.caption("จุดน้ำเงิน=คดี เส้นส้ม=คดีที่ใช้จุดร่วมเดียวกัน ใช้ดูว่าควรไปทำมวลชนสัมพันธ์/เตือนภัยที่พื้นที่ใด")
    cases = db.get_cases("cyber")
    pairs = db.get_all_link_pairs("cyber")
    if HAS_MAP:
        m = map_view.build_cyber_map(db.get_stations(), cases, pairs, db.get_boundaries())
        st_folium(m, width=None, height=520, returned_objects=[])
    else:
        st.warning("ยังไม่ได้ติดตั้งแผนที่ ให้รัน: python -m pip install folium streamlit-folium")
    st.divider()
    section_title("รายการคู่คดีที่เชื่อมโยง")
    byid = {c["case_id"]: c for c in cases}
    for a, b, n in pairs:
        st.markdown(f'🔗 **{byid[a]["case_number"]}** ({byid[a]["station_code"]}) — '
                    f'**{byid[b]["case_number"]}** ({byid[b]["station_code"]}) · {n} จุดร่วม')


# ---------------------------------------------------------------- หน้า: แผนผังสายตรวจ
def page_physical_map():
    section_title("🚓 แผนผังสายตรวจ — คดีในพื้นที่")
    st.caption("วงสี=จุดเสี่ยง (แดง=สูง ส้ม=กลาง เขียว=ต่ำ) จุดแดง=คดี เส้นประส้ม=คดีที่เชื่อมโยงข้ามพื้นที่")
    cases = db.get_cases("physical")

    # กรองตามช่วงเวลา (มีประโยชน์กับการจัดผลัดสายตรวจ)
    tb = st.selectbox("กรองตามช่วงเวลาเกิดเหตุ", ["ทั้งหมด"] + TIME_BUCKETS)
    if tb != "ทั้งหมด":
        cases = [c for c in cases if c.get("time_bucket") == tb]

    pairs = db.get_all_link_pairs("physical")
    ids = {c["case_id"] for c in cases}
    pairs = [(a, b, n) for a, b, n in pairs if a in ids and b in ids]

    if HAS_MAP:
        m = map_view.build_physical_map(db.get_stations(), cases,
                                        db.get_risk_points("physical"), pairs, db.get_boundaries())
        st_folium(m, width=None, height=520, returned_objects=[])
    else:
        st.warning("ยังไม่ได้ติดตั้งแผนที่ ให้รัน: python -m pip install folium streamlit-folium")

    st.divider()
    section_title("ระดับความเสี่ยงรายพื้นที่")
    for d in db.risk_by_area("physical"):
        c1, c2, c3 = st.columns([2, 1, 1.3])
        c1.write(d["area"]); c2.write(f'{d["case_count"]} คดี')
        c3.markdown(risk_badge(d["risk_level"]), unsafe_allow_html=True)


# ---------------------------------------------------------------- หน้า: จัดการพื้นที่/จุดเสี่ยง
def page_manage_area():
    section_title("🗺️ จัดการพื้นที่ / จุดเสี่ยง")
    t1, t2, t3 = st.tabs(["สถานี & ทิศ & พิกัด", "จุดเสี่ยง", "ขอบเขตแผนที่ (KML)"])

    # --- สถานี ---
    with t1:
        st.caption("แก้ชื่อ/ทิศ/พิกัดได้ในตาราง เพิ่มแถวใหม่ได้ ลบแถวด้วยไอคอนถังขยะ แล้วกดบันทึก")
        df = pd.DataFrame(db.get_stations())[["code", "name", "direction", "lat", "lng", "is_main"]]
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                column_config={
                                    "code": "รหัส สน.", "name": "ชื่อ",
                                    "direction": st.column_config.SelectboxColumn("ทิศ", options=DIRECTIONS),
                                    "lat": "lat", "lng": "lng",
                                    "is_main": st.column_config.CheckboxColumn("สน.หลัก")})
        if st.button("💾 บันทึกสถานี"):
            db.save_stations(edited.to_dict("records")); st.success("บันทึกแล้ว"); st.rerun()

    # --- จุดเสี่ยง ---
    with t2:
        cat_label = st.radio("กลุ่ม", ["คดีในพื้นที่", "ไซเบอร์"], horizontal=True, key="rp_cat")
        cat = "physical" if cat_label == "คดีในพื้นที่" else "cyber"
        pts = db.get_risk_points(cat)
        df = pd.DataFrame(pts)[["name", "lat", "lng", "level", "note"]] if pts else \
            pd.DataFrame(columns=["name", "lat", "lng", "level", "note"])
        st.caption("เพิ่ม/แก้/ย้าย(แก้พิกัด)/ลบจุดเสี่ยงได้ในตาราง แล้วกดบันทึก")
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                column_config={
                                    "name": "ชื่อจุด", "lat": "lat", "lng": "lng",
                                    "level": st.column_config.SelectboxColumn("ระดับเสี่ยง", options=RISK_LEVELS),
                                    "note": "หมายเหตุ"})
        if st.button("💾 บันทึกจุดเสี่ยง"):
            db.save_risk_points(cat, edited.to_dict("records")); st.success("บันทึกแล้ว"); st.rerun()

        if HAS_MAP and pts:
            st.caption("ตำแหน่งจุดเสี่ยงปัจจุบัน")
            st_folium(map_view.simple_points_map(pts), height=380, returned_objects=[])

    # --- ขอบเขต KML (หลาย สน.) ---
    with t3:
        st.caption("นำเข้าไฟล์ขอบเขตจาก Google My Maps — รองรับหลาย สน. ในไฟล์เดียว (แต่ละ Placemark = 1 พื้นที่)")
        st.markdown("**วิธีได้ไฟล์:** เปิด Google My Maps → เมนู ⋮ → Export to KML/KMZ → "
                    "อัปโหลดด้านล่าง (รองรับ .kml/.kmz/.geojson) ระบบจะอ่านชื่อแต่ละพื้นที่ให้เอง")
        up = st.file_uploader("อัปโหลดไฟล์ขอบเขต", type=["kml", "kmz", "geojson", "json"])
        if up is not None:
            try:
                named = geo.parse_named_boundaries(up.name, up.getvalue())
                if named:
                    areas = []
                    for a in named:
                        nm = a["name"] or ""
                        code = nm if nm and nm != "Polygon 1" else "สน.ลุมพินี"
                        is_main = 1 if "ลุมพินี" in code or nm == "Polygon 1" else 0
                        areas.append({"code": code, "name": nm, "is_main": is_main,
                                      "polygon": a["polygon"]})
                    db.set_boundaries(areas)
                    st.success(f"นำเข้าขอบเขต {len(areas)} พื้นที่เรียบร้อย")
                else:
                    st.error("อ่านขอบเขตจากไฟล์ไม่ได้ ลองตรวจรูปแบบไฟล์")
            except Exception as e:
                st.error(f"นำเข้าไม่สำเร็จ: {e}")

        cur = db.get_boundaries()
        if cur:
            st.write(f"ขอบเขตปัจจุบัน {len(cur)} พื้นที่:")
            st.dataframe(pd.DataFrame([{"พื้นที่": b.get("code", ""),
                                        "สน.หลัก": "✓" if b.get("is_main") else "",
                                        "จำนวนจุด": len(b.get("polygon", []))} for b in cur]),
                         use_container_width=True, hide_index=True)
        if st.button("คืนค่าขอบเขตตั้งต้น"):
            db.set_boundaries(seed_data.BOUNDARIES); st.success("คืนค่าแล้ว"); st.rerun()
        if HAS_MAP and cur:
            st.caption("พรีวิวขอบเขตทั้งหมด")
            st_folium(map_view._base_map(cur), height=420, returned_objects=[])


# ---------------------------------------------------------------- หน้า: ค้นหา
def page_search():
    section_title("🔍 ค้นหาจุดร่วม")
    types = list(db.INDICATOR_LABELS.keys())
    c1, c2 = st.columns([1, 2])
    t = c1.selectbox("ชนิด", types, format_func=lambda k: db.INDICATOR_LABELS[k])
    kw = c2.text_input("ค่าที่ค้นหา")
    if st.button("ค้นหา") and kw.strip():
        norm = db.normalize_value(t, kw)
        conn = db.get_conn()
        rows = conn.execute("""SELECT c.case_number,c.category,s.code AS st,c.crime_type,i.raw_value
                               FROM indicators i JOIN cases c ON i.case_id=c.case_id
                               JOIN stations s ON c.station_id=s.station_id
                               WHERE i.indicator_type=? AND i.norm_value=?""", (t, norm)).fetchall()
        conn.close()
        if rows:
            st.success(f"พบ {len(rows)} คดี")
            st.dataframe(pd.DataFrame([{"เลขคดี": r["case_number"],
                                        "กลุ่ม": "ไซเบอร์" if r["category"] == "cyber" else "พื้นที่",
                                        "สถานี": r["st"], "ประเภท": r["crime_type"],
                                        "ค่า": r["raw_value"]} for r in rows]),
                         use_container_width=True, hide_index=True)
            if len(rows) > 1:
                st.warning("⚠️ จุดร่วมนี้ปรากฏหลายคดี — อาจเป็นคนร้ายรายเดียวกัน")
        else:
            st.info("ไม่พบ")


# ---------------------------------------------------------------- เมนู/ราวเตอร์
with st.sidebar:
    st.markdown("### เมนูหลัก")
    page = st.radio("ไปยังหน้า", [
        "📊 แดชบอร์ด", "📝 บันทึกคดี", "✏️ จัดการ/แก้ไขคดี",
        "🌐 แผนผังไซเบอร์ (มวลชนสัมพันธ์)", "🚓 แผนผังสายตรวจ (คดีพื้นที่)",
        "🗺️ จัดการพื้นที่/จุดเสี่ยง", "🔍 ค้นหา",
    ], label_visibility="collapsed")
    st.divider()
    if st.button("♻️ รีเซ็ตข้อมูลตัวอย่าง", use_container_width=True):
        seed_data.reset_and_seed(); st.success("โหลดใหม่แล้ว"); st.rerun()

if page.startswith("📊"): page_dashboard()
elif page.startswith("📝"): page_new()
elif page.startswith("✏️"): page_manage_cases()
elif page.startswith("🌐"): page_cyber_map()
elif page.startswith("🚓"): page_physical_map()
elif page.startswith("🗺️"): page_manage_area()
elif page.startswith("🔍"): page_search()
