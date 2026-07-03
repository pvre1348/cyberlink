"""
database.py — ชั้นข้อมูลของ CyberLink (เวอร์ชัน Supabase / PostgreSQL)
คงชื่อฟังก์ชันเดิมทั้งหมดไว้ เพื่อให้ app.py ใช้งานได้เหมือนตอนเป็น SQLite
ตรรกะที่ซับซ้อน (เชื่อมโยงคดี, สรุปพื้นที่เสี่ยง) คำนวณฝั่ง Python เพราะข้อมูลไม่ใหญ่
"""
import re
import json

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

    # เซ็ตของ (type, norm) ของคดีนี้
    my_keys = {(i["indicator_type"], i["norm_value"]) for i in my_inds}
    linked = {}
    for ind in all_inds:
        if ind["case_id"] == case_id:
            continue
        key = (ind["indicator_type"], ind["norm_value"])
        if key not in my_keys:
            continue
        other = cases.get(ind["case_id"])
        if not other or other["category"] != me["category"]:
            continue
        oid = ind["case_id"]
        if oid not in linked:
            linked[oid] = {"case_id": oid, "case_number": other["case_number"],
                           "station_code": other["station_code"],
                           "crime_type": other["crime_type"],
                           "lat": other.get("lat"), "lng": other.get("lng"), "shared": []}
        linked[oid]["shared"].append({
            "type": ind["indicator_type"],
            "label": INDICATOR_LABELS.get(ind["indicator_type"], ind["indicator_type"]),
            "value": ind["raw_value"]})
    return list(linked.values())


def get_all_link_pairs(category):
    all_inds = _all_indicators()
    cases = {c["case_id"]: c for c in get_cases(category)}
    # เก็บ case ต่อ (type, norm)
    bucket = {}
    for ind in all_inds:
        if ind["case_id"] not in cases:
            continue
        bucket.setdefault((ind["indicator_type"], ind["norm_value"]), set()).add(ind["case_id"])
    # นับจุดร่วมระหว่างคู่คดี
    pair_count = {}
    for cids in bucket.values():
        cid_list = sorted(cids)
        for i in range(len(cid_list)):
            for j in range(i + 1, len(cid_list)):
                pair_count[(cid_list[i], cid_list[j])] = pair_count.get((cid_list[i], cid_list[j]), 0) + 1
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
    for d in data:
        d["score"] = d["case_count"] + d["sev_sum"]
    mx = max(d["score"] for d in data)
    for d in data:
        ratio = d["score"] / mx if mx else 0
        d["risk_level"] = "สูง" if ratio >= 0.66 else ("ปานกลาง" if ratio >= 0.33 else "ต่ำ")
    data.sort(key=lambda d: d["score"], reverse=True)
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
