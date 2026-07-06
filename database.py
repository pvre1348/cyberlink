"""
database.py — ชั้นข้อมูลของ CyberLink (เวอร์ชัน Supabase / PostgreSQL)
คงชื่อฟังก์ชันเดิมทั้งหมดไว้ เพื่อให้ app.py ใช้งานได้เหมือนตอนเป็น SQLite
ตรรกะที่ซับซ้อน (เชื่อมโยงคดี, สรุปพื้นที่เสี่ยง) คำนวณฝั่ง Python เพราะข้อมูลไม่ใหญ่
"""
import re
import json
from difflib import SequenceMatcher

import supa

# ---------------- ป้ายชื่อจุดร่วม ----------------
INDICATOR_LABELS = {
    "bank_account": "เลขบัญชีธนาคาร",
    "account_name": "ชื่อบัญชี",
    "phone": "เบอร์โทรศัพท์",
    "line_id": "ไอดีไลน์",
    "url": "URL / เพจ",
    "vehicle_plate": "ทะเบียนรถ",
    "suspect_desc": "ลักษณะคนร้าย",
    "other": "อื่น ๆ",
}
CYBER_INDICATORS = ["bank_account", "account_name", "phone", "line_id", "url", "other"]
PHYSICAL_INDICATORS = ["vehicle_plate", "suspect_desc", "phone", "other"]

CASE_FIELDS = ("case_number", "station_id", "category", "crime_type", "report_date",
               "time_bucket", "area", "location_detail", "lat", "lng",
               "victim_name", "damage_amount", "weapon", "severity", "mo_description")


def sb():
    return supa.service_client()


# ---------------- normalize ----------------
def normalize_value(indicator_type, value):
    if value is None:
        return ""
    v = value.strip()
    if indicator_type in ("bank_account", "phone"):
        return re.sub(r"\D", "", v)
    if indicator_type == "vehicle_plate":
        return re.sub(r"[\s\-]", "", v).upper()
    if indicator_type == "line_id":
        return v.lstrip("@").replace(" ", "").lower()
    return re.sub(r"\s+", " ", v).strip().lower()


# ---------------- fuzzy matching (สำหรับข้อความอิสระ เช่น ลักษณะคนร้าย) ----------------
# ชนิดจุดร่วมที่ใช้การเทียบแบบใกล้เคียงแทนการเทียบตรงตัว
FUZZY_TYPES = {"suspect_desc"}
FUZZY_THRESHOLD = 0.82   # ความคล้ายขั้นต่ำ (0-1) ~82%


def _similar(a, b):
    """เทียบความคล้ายของข้อความ 2 ชุดด้วย SequenceMatcher
    เช่น 'ชายผอมสูง สวมหมวก' กับ 'ชายผอมสูง หมวก' -> ~0.90 ถือว่าตรงกัน"""
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() >= FUZZY_THRESHOLD


# ---------------- settings / boundaries ----------------
def set_setting(key, value):
    sb().table("settings").upsert({"key": key, "value": value}).execute()


def get_setting(key, default=None):
    r = sb().table("settings").select("value").eq("key", key).execute()
    if r.data:
        return r.data[0]["value"]
    return default


def get_boundaries():
    raw = get_setting("boundaries")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def set_boundaries(areas):
    set_setting("boundaries", json.dumps(areas, ensure_ascii=False))


# คงไว้เพื่อความเข้ากันได้ (โค้ดเก่าบางส่วนเรียก)
def get_boundary():
    return [a["polygon"] for a in get_boundaries()]


def set_boundary(polygons):
    set_boundaries([{"code": f"พื้นที่ {i+1}", "name": "", "is_main": 0, "polygon": p}
                    for i, p in enumerate(polygons)])


# ---------------- รายการย่านมาตรฐาน (เก็บใน settings — ไม่แก้ schema) ----------------
DEFAULT_NEIGHBORHOODS = [
    "ลุมพินี", "วิทยุ", "เพลินจิต", "ชิดลม", "ราชประสงค์",
    "ราชดำริ", "หลังสวน", "ต้นสน", "สารสิน", "ร่วมฤดี", "พระราม 4 (ฝั่งเหนือ)",
]


def get_neighborhoods():
    """คืนรายการย่านมาตรฐานสำหรับ dropdown (ถ้ายังไม่เคยบันทึก ใช้ค่าตั้งต้น)"""
    raw = get_setting("neighborhoods")
    if raw:
        try:
            lst = json.loads(raw)
            if lst:
                return lst
        except Exception:
            pass
    return list(DEFAULT_NEIGHBORHOODS)


def save_neighborhoods(items):
    """บันทึกรายการย่าน (ตัดค่าว่าง/ซ้ำออก คงลำดับเดิม)"""
    clean = []
    for x in items:
        x = (x or "").strip()
        if x and x not in clean:
            clean.append(x)
    set_setting("neighborhoods", json.dumps(clean, ensure_ascii=False))


# ---------------- stations ----------------
def add_station(code, name, direction="", lat=None, lng=None, is_main=0):
    sb().table("stations").insert({
        "code": code, "name": name, "direction": direction,
        "lat": lat, "lng": lng, "is_main": int(is_main or 0)}).execute()


def get_stations():
    r = sb().table("stations").select("*").order("is_main", desc=True).order("code").execute()
    return r.data or []


def save_stations(rows):
    client = sb()
    client.table("stations").delete().neq("station_id", -1).execute()  # ลบทั้งหมด
    payload = []
    for r in rows:
        if not (r.get("code") and r.get("name")):
            continue
        payload.append({"code": r.get("code"), "name": r.get("name"),
                        "direction": r.get("direction", ""), "lat": r.get("lat"),
                        "lng": r.get("lng"), "is_main": int(r.get("is_main", 0) or 0)})
    if payload:
        client.table("stations").insert(payload).execute()


# ---------------- cases ----------------
def add_case(indicators=None, created_by=None, **f):
    row = {k: f.get(k) for k in CASE_FIELDS}
    if created_by:
        row["created_by"] = created_by
    r = sb().table("cases").insert(row).execute()
    case_id = r.data[0]["case_id"]
    _write_indicators(case_id, indicators or [])
    return case_id


def update_case(case_id, indicators=None, **f):
    row = {k: f.get(k) for k in CASE_FIELDS}
    sb().table("cases").update(row).eq("case_id", case_id).execute()
    sb().table("indicators").delete().eq("case_id", case_id).execute()
    _write_indicators(case_id, indicators or [])


def _write_indicators(case_id, indicators):
    payload = []
    for ind_type, raw in indicators:
        raw = (raw or "").strip()
        if not raw:
            continue
        norm = normalize_value(ind_type, raw)
        if not norm:
            continue
        payload.append({"case_id": case_id, "indicator_type": ind_type,
                        "raw_value": raw, "norm_value": norm})
    if payload:
        sb().table("indicators").insert(payload).execute()


def delete_case(case_id):
    sb().table("indicators").delete().eq("case_id", case_id).execute()
    sb().table("cases").delete().eq("case_id", case_id).execute()


def _station_map():
    return {s["station_id"]: s for s in get_stations()}


def _attach_station(case, smap):
    s = smap.get(case.get("station_id"), {})
    case["station_code"] = s.get("code", "")
    case["station_name"] = s.get("name", "")
    case["station_direction"] = s.get("direction", "")
    return case


def get_cases(category=None):
    q = sb().table("cases").select("*")
    if category:
        q = q.eq("category", category)
    r = q.order("report_date", desc=True).order("case_id", desc=True).execute()
    smap = _station_map()
    return [_attach_station(dict(c), smap) for c in (r.data or [])]


def get_case(case_id):
    r = sb().table("cases").select("*").eq("case_id", case_id).execute()
    if not r.data:
        return None
    smap = _station_map()
    return _attach_station(dict(r.data[0]), smap)


def get_indicators(case_id):
    r = sb().table("indicators").select("*").eq("case_id", case_id).execute()
    return r.data or []


def get_indicators_grouped(case_id):
    grouped = {k: [] for k in INDICATOR_LABELS}
    for ind in get_indicators(case_id):
        if ind["indicator_type"] in grouped:
            grouped[ind["indicator_type"]].append(ind["raw_value"])
    return {k: "\n".join(v) for k, v in grouped.items()}


# ---------------- หัวใจ: เชื่อมโยงคดี ----------------
def _all_indicators():
    r = sb().table("indicators").select("*").execute()
    return r.data or []


def detect_links(case_id):
    me = get_case(case_id)
    if not me:
        return []
    my_inds = get_indicators(case_id)
    if not my_inds:
        return []
    all_inds = _all_indicators()
    cases = {c["case_id"]: c for c in get_cases()}   # มี station_code แล้ว

    # แยกจุดร่วมของคดีนี้: แบบเทียบตรงตัว vs แบบเทียบใกล้เคียง (fuzzy)
    my_exact = {(i["indicator_type"], i["norm_value"])
                for i in my_inds if i["indicator_type"] not in FUZZY_TYPES}
    my_fuzzy = [i for i in my_inds if i["indicator_type"] in FUZZY_TYPES]

    linked = {}

    def add_match(ind):
        oid = ind["case_id"]
        other = cases.get(oid)
        if not other or other["category"] != me["category"]:
            return
        if oid not in linked:
            linked[oid] = {"case_id": oid, "case_number": other["case_number"],
                           "station_code": other["station_code"],
                           "crime_type": other["crime_type"],
                           "lat": other.get("lat"), "lng": other.get("lng"), "shared": []}
        linked[oid]["shared"].append({
            "type": ind["indicator_type"],
            "label": INDICATOR_LABELS.get(ind["indicator_type"], ind["indicator_type"]),
            "value": ind["raw_value"]})

    for ind in all_inds:
        if ind["case_id"] == case_id:
            continue
        t = ind["indicator_type"]
        if t in FUZZY_TYPES:
            # เทียบแบบใกล้เคียงกับจุดร่วม fuzzy ของคดีนี้ทุกตัว
            for mine in my_fuzzy:
                if mine["indicator_type"] == t and _similar(mine["norm_value"], ind["norm_value"]):
                    add_match(ind)
                    break
        elif (t, ind["norm_value"]) in my_exact:
            add_match(ind)
    return list(linked.values())


def get_all_link_pairs(category):
    all_inds = _all_indicators()
    case_ids = {c["case_id"] for c in get_cases(category)}
    exact = [i for i in all_inds
             if i["case_id"] in case_ids and i["indicator_type"] not in FUZZY_TYPES]
    fuzzy = [i for i in all_inds
             if i["case_id"] in case_ids and i["indicator_type"] in FUZZY_TYPES]

    pair_count = {}

    # 1) จับคู่แบบตรงตัว: เก็บ case ต่อ (type, norm)
    bucket = {}
    for ind in exact:
        bucket.setdefault((ind["indicator_type"], ind["norm_value"]), set()).add(ind["case_id"])
    for cids in bucket.values():
        lst = sorted(cids)
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                key = (lst[i], lst[j])
                pair_count[key] = pair_count.get(key, 0) + 1

    # 2) จับคู่แบบใกล้เคียง (fuzzy) สำหรับลักษณะคนร้าย: เทียบทีละคู่
    for i in range(len(fuzzy)):
        for j in range(i + 1, len(fuzzy)):
            a, b = fuzzy[i], fuzzy[j]
            if a["case_id"] == b["case_id"]:
                continue
            if a["indicator_type"] != b["indicator_type"]:
                continue
            if _similar(a["norm_value"], b["norm_value"]):
                key = tuple(sorted((a["case_id"], b["case_id"])))
                pair_count[key] = pair_count.get(key, 0) + 1

    return [(a, b, n) for (a, b), n in pair_count.items()]


# ---------------- risk points ----------------
def get_risk_points(category=None):
    q = sb().table("risk_points").select("*")
    if category:
        q = q.eq("category", category)
    return q.execute().data or []


def add_risk_point(category, name, lat, lng, level="ปานกลาง", note=""):
    sb().table("risk_points").insert({
        "category": category, "name": name, "lat": lat, "lng": lng,
        "level": level, "note": note}).execute()


def save_risk_points(category, rows):
    client = sb()
    client.table("risk_points").delete().eq("category", category).execute()
    payload = []
    for r in rows:
        if r.get("name") is None or r.get("lat") is None or r.get("lng") is None:
            continue
        payload.append({"category": category, "name": r.get("name"),
                        "lat": r.get("lat"), "lng": r.get("lng"),
                        "level": r.get("level", "ปานกลาง"), "note": r.get("note", "")})
    if payload:
        client.table("risk_points").insert(payload).execute()


# ---------------- สถิติ / วิเคราะห์ ----------------
def level_for_count(n):
    """เกณฑ์ระดับความเสี่ยงตัวเลขตายตัว (ตรงกับสีวงบนแผนที่)
    ≤3 คดี = ต่ำ | 4-5 คดี = ปานกลาง | >5 คดี = สูง"""
    if n > 5:
        return "สูง"
    if n >= 4:
        return "ปานกลาง"
    return "ต่ำ"


def risk_by_area(category):
    cases = get_cases(category)
    agg = {}
    for c in cases:
        area = c.get("area")
        if not area:
            continue
        a = agg.setdefault(area, {"area": area, "case_count": 0, "sev_sum": 0, "total_damage": 0})
        a["case_count"] += 1
        a["sev_sum"] += (c.get("severity") or 1)
        a["total_damage"] += (c.get("damage_amount") or 0)
    data = list(agg.values())
    if not data:
        return []
    # ใช้เกณฑ์ตัวเลขตายตัว (เลิกเทียบสัมพัทธ์กับพื้นที่ที่มีคดีมากสุด)
    for d in data:
        d["risk_level"] = level_for_count(d["case_count"])
    data.sort(key=lambda d: d["case_count"], reverse=True)
    return data


def get_dashboard_stats():
    cases = get_cases()
    cyber = [c for c in cases if c["category"] == "cyber"]
    physical = [c for c in cases if c["category"] == "physical"]
    return {
        "cyber_cases": len(cyber),
        "physical_cases": len(physical),
        "total_damage": sum(c.get("damage_amount") or 0 for c in cyber),
        "total_indicators": len(_all_indicators()),
        "cyber_links": len(get_all_link_pairs("cyber")),
        "physical_links": len(get_all_link_pairs("physical")),
    }


def get_top_reused_indicators(category, limit=8):
    all_inds = _all_indicators()
    cases = {c["case_id"] for c in get_cases(category)}
    bucket = {}
    for ind in all_inds:
        if ind["case_id"] not in cases:
            continue
        key = (ind["indicator_type"], ind["norm_value"])
        b = bucket.setdefault(key, {"indicator_type": ind["indicator_type"],
                                    "raw_value": ind["raw_value"], "cases": set()})
        b["cases"].add(ind["case_id"])
    result = [{"indicator_type": b["indicator_type"], "raw_value": b["raw_value"],
               "used": len(b["cases"])} for b in bucket.values() if len(b["cases"]) > 1]
    result.sort(key=lambda x: x["used"], reverse=True)
    return result[:limit]


# ---------------- โครงสร้างพื้นฐาน (สถานี+ขอบเขต) ----------------
def stations_empty():
    return len(get_stations()) == 0


def cases_empty():
    r = sb().table("cases").select("case_id").limit(1).execute()
    return not r.data
