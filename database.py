"""
database.py — ฐานข้อมูลระบบ CyberLink / PatrolLink
รองรับ 2 กลุ่มคดี:
  - cyber    : อาชญากรรมไซเบอร์ (เชื่อมโยงด้วย บัญชี/ไลน์/เบอร์) -> ใช้ทำมวลชนสัมพันธ์
  - physical : คดีในพื้นที่ ลัก/วิ่งราว/ชิง/ปล้น/จลาจล (เชื่อมโยงด้วย ทะเบียนรถ/ลักษณะคนร้าย) -> ใช้บริหารสายตรวจ

แนวคิดในรายวิชาที่ใช้: ตัวแปร/ชนิดข้อมูล, if-else, for loop, ฟังก์ชัน,
list/dict/set, การจัดการฐานข้อมูล (sqlite3), การอ่าน/เขียนไฟล์ (import KML)
"""
import sqlite3
import re
import json

DB_PATH = "policelink.db"

# ป้ายชื่อชนิดจุดร่วม
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
# จุดร่วมที่ใช้ในแต่ละกลุ่มคดี
CYBER_INDICATORS = ["bank_account", "account_name", "phone", "line_id", "url", "other"]
PHYSICAL_INDICATORS = ["vehicle_plate", "suspect_desc", "phone", "other"]


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stations (
            station_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            direction TEXT,
            lat REAL, lng REAL,
            is_main INTEGER DEFAULT 0
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_number TEXT NOT NULL,
            station_id INTEGER NOT NULL,
            category TEXT NOT NULL,             -- cyber | physical
            crime_type TEXT NOT NULL,
            report_date TEXT NOT NULL,
            time_bucket TEXT,                   -- เช้า/บ่าย/ค่ำ/ดึก
            area TEXT,
            location_detail TEXT,
            lat REAL, lng REAL,
            victim_name TEXT,
            damage_amount REAL DEFAULT 0,
            weapon TEXT,
            severity INTEGER DEFAULT 1,         -- 1-3 ความรุนแรง (ใช้ถ่วงน้ำหนักความเสี่ยง)
            mo_description TEXT,
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (station_id) REFERENCES stations(station_id)
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS indicators (
            indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            indicator_type TEXT NOT NULL,
            raw_value TEXT NOT NULL,
            norm_value TEXT NOT NULL,
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS risk_points (
            point_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,             -- cyber | physical
            name TEXT NOT NULL,
            lat REAL NOT NULL, lng REAL NOT NULL,
            level TEXT DEFAULT 'ปานกลาง',       -- สูง/ปานกลาง/ต่ำ
            note TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ind ON indicators(indicator_type, norm_value)")
    conn.commit()
    conn.close()


# ---------- normalize ----------
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


# ---------- settings (เก็บขอบเขตแผนที่) ----------
def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def get_boundary():
    """(คงไว้เพื่อความเข้ากันได้) คืนเฉพาะ polygon ทั้งหมดแบบไม่มีชื่อ"""
    return [a["polygon"] for a in get_boundaries()]


def set_boundary(polygons):
    """(คงไว้เพื่อความเข้ากันได้) เก็บ polygon เป็นพื้นที่ไม่มีชื่อ"""
    areas = [{"code": f"พื้นที่ {i+1}", "name": "", "is_main": 0, "polygon": p}
             for i, p in enumerate(polygons)]
    set_boundaries(areas)


def get_boundaries():
    """คืนรายการขอบเขตแบบมีชื่อ: [{code,name,is_main,polygon}, ...]"""
    raw = get_setting("boundaries")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def set_boundaries(areas):
    """บันทึกรายการขอบเขตหลาย สน. (แต่ละอันมี code/name/is_main/polygon)"""
    set_setting("boundaries", json.dumps(areas, ensure_ascii=False))


# ---------- stations ----------
def add_station(code, name, direction="", lat=None, lng=None, is_main=0):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO stations(code,name,direction,lat,lng,is_main) "
                     "VALUES(?,?,?,?,?,?)", (code, name, direction, lat, lng, is_main))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def get_stations():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM stations ORDER BY is_main DESC, code").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_stations(rows):
    """บันทึกตารางสถานีทั้งหมด (ใช้กับ data_editor): ลบเก่าทิ้งแล้วเขียนใหม่"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM stations")
    for r in rows:
        if not (r.get("code") and r.get("name")):
            continue
        cur.execute("INSERT INTO stations(code,name,direction,lat,lng,is_main) VALUES(?,?,?,?,?,?)",
                    (r.get("code"), r.get("name"), r.get("direction", ""),
                     r.get("lat"), r.get("lng"), int(r.get("is_main", 0) or 0)))
    conn.commit()
    conn.close()


# ---------- cases ----------
CASE_FIELDS = ("case_number", "station_id", "category", "crime_type", "report_date",
               "time_bucket", "area", "location_detail", "lat", "lng",
               "victim_name", "damage_amount", "weapon", "severity", "mo_description")


def add_case(indicators=None, **f):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""INSERT INTO cases ({",".join(CASE_FIELDS)})
                    VALUES ({",".join("?" for _ in CASE_FIELDS)})""",
                tuple(f.get(k) for k in CASE_FIELDS))
    case_id = cur.lastrowid
    _write_indicators(cur, case_id, indicators or [])
    conn.commit()
    conn.close()
    return case_id


def update_case(case_id, indicators=None, **f):
    conn = get_conn()
    cur = conn.cursor()
    sets = ",".join(f"{k}=?" for k in CASE_FIELDS)
    cur.execute(f"UPDATE cases SET {sets} WHERE case_id=?",
                tuple(f.get(k) for k in CASE_FIELDS) + (case_id,))
    cur.execute("DELETE FROM indicators WHERE case_id=?", (case_id,))
    _write_indicators(cur, case_id, indicators or [])
    conn.commit()
    conn.close()


def _write_indicators(cur, case_id, indicators):
    for ind_type, raw in indicators:
        raw = (raw or "").strip()
        if not raw:
            continue
        norm = normalize_value(ind_type, raw)
        if not norm:
            continue
        cur.execute("INSERT INTO indicators(case_id,indicator_type,raw_value,norm_value) "
                    "VALUES(?,?,?,?)", (case_id, ind_type, raw, norm))


def delete_case(case_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM indicators WHERE case_id=?", (case_id,))
    cur.execute("DELETE FROM cases WHERE case_id=?", (case_id,))
    conn.commit()
    conn.close()


def get_cases(category=None):
    conn = get_conn()
    sql = """SELECT c.*, s.code AS station_code, s.name AS station_name,
                    s.direction AS station_direction
             FROM cases c JOIN stations s ON c.station_id=s.station_id"""
    params = ()
    if category:
        sql += " WHERE c.category=?"
        params = (category,)
    sql += " ORDER BY c.report_date DESC, c.case_id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_case(case_id):
    conn = get_conn()
    row = conn.execute("""SELECT c.*, s.code AS station_code, s.direction AS station_direction
                          FROM cases c JOIN stations s ON c.station_id=s.station_id
                          WHERE c.case_id=?""", (case_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_indicators(case_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM indicators WHERE case_id=?", (case_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_indicators_grouped(case_id):
    grouped = {k: [] for k in INDICATOR_LABELS}
    for ind in get_indicators(case_id):
        if ind["indicator_type"] in grouped:
            grouped[ind["indicator_type"]].append(ind["raw_value"])
    return {k: "\n".join(v) for k, v in grouped.items()}


# ---------- หัวใจ: เชื่อมโยงคดี (แยกตามกลุ่มคดี) ----------
def detect_links(case_id):
    me = get_case(case_id)
    if not me:
        return []
    my_inds = get_indicators(case_id)
    if not my_inds:
        return []
    conn = get_conn()
    linked = {}
    for ind in my_inds:
        rows = conn.execute("""
            SELECT c.case_id, c.case_number, c.crime_type, c.lat, c.lng,
                   s.code AS station_code, i.indicator_type, i.raw_value
            FROM indicators i
            JOIN cases c ON i.case_id=c.case_id
            JOIN stations s ON c.station_id=s.station_id
            WHERE i.indicator_type=? AND i.norm_value=?
              AND i.case_id!=? AND c.category=?
        """, (ind["indicator_type"], ind["norm_value"], case_id, me["category"])).fetchall()
        for r in rows:
            oid = r["case_id"]
            if oid not in linked:
                linked[oid] = {"case_id": oid, "case_number": r["case_number"],
                               "station_code": r["station_code"], "crime_type": r["crime_type"],
                               "lat": r["lat"], "lng": r["lng"], "shared": []}
            linked[oid]["shared"].append({
                "type": r["indicator_type"],
                "label": INDICATOR_LABELS.get(r["indicator_type"], r["indicator_type"]),
                "value": r["raw_value"]})
    conn.close()
    return list(linked.values())


def get_all_link_pairs(category):
    """คู่คดีที่เชื่อมโยงกันในกลุ่มที่ระบุ -> (case_id_a, case_id_b, จำนวนจุดร่วม)"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.case_id AS a_id, b.case_id AS b_id, COUNT(*) AS n
        FROM indicators a
        JOIN indicators b ON a.indicator_type=b.indicator_type
                         AND a.norm_value=b.norm_value AND a.case_id<b.case_id
        JOIN cases ca ON a.case_id=ca.case_id
        JOIN cases cb ON b.case_id=cb.case_id
        WHERE ca.category=? AND cb.category=?
        GROUP BY a.case_id, b.case_id
    """, (category, category)).fetchall()
    conn.close()
    return [(r["a_id"], r["b_id"], r["n"]) for r in rows]


# ---------- risk points ----------
def get_risk_points(category=None):
    conn = get_conn()
    if category:
        rows = conn.execute("SELECT * FROM risk_points WHERE category=?", (category,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM risk_points").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_risk_point(category, name, lat, lng, level="ปานกลาง", note=""):
    conn = get_conn()
    conn.execute("INSERT INTO risk_points(category,name,lat,lng,level,note) VALUES(?,?,?,?,?,?)",
                 (category, name, lat, lng, level, note))
    conn.commit()
    conn.close()


def save_risk_points(category, rows):
    """บันทึกจุดเสี่ยงทั้งหมดของกลุ่ม (ใช้กับ data_editor): add/move/delete ในครั้งเดียว"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM risk_points WHERE category=?", (category,))
    for r in rows:
        if r.get("name") is None or r.get("lat") is None or r.get("lng") is None:
            continue
        cur.execute("INSERT INTO risk_points(category,name,lat,lng,level,note) VALUES(?,?,?,?,?,?)",
                    (category, r.get("name"), r.get("lat"), r.get("lng"),
                     r.get("level", "ปานกลาง"), r.get("note", "")))
    conn.commit()
    conn.close()


# ---------- สถิติ / วิเคราะห์ ----------
def risk_by_area(category):
    conn = get_conn()
    rows = conn.execute("""
        SELECT area, COUNT(*) AS case_count,
               COALESCE(SUM(severity),0) AS sev_sum,
               COALESCE(SUM(damage_amount),0) AS total_damage
        FROM cases WHERE category=? AND area IS NOT NULL AND area!=''
        GROUP BY area""", (category,)).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    if not data:
        return []
    for d in data:
        # คะแนนเสี่ยง = จำนวนคดี + ความรุนแรงรวม (ถ่วงน้ำหนัก)
        d["score"] = d["case_count"] + d["sev_sum"]
    mx = max(d["score"] for d in data)
    for d in data:
        ratio = d["score"] / mx if mx else 0
        d["risk_level"] = "สูง" if ratio >= 0.66 else ("ปานกลาง" if ratio >= 0.33 else "ต่ำ")
    data.sort(key=lambda d: d["score"], reverse=True)
    return data


def get_dashboard_stats():
    conn = get_conn()
    def one(q, p=()):
        return conn.execute(q, p).fetchone()[0]
    stats = {
        "cyber_cases": one("SELECT COUNT(*) FROM cases WHERE category='cyber'"),
        "physical_cases": one("SELECT COUNT(*) FROM cases WHERE category='physical'"),
        "total_damage": one("SELECT COALESCE(SUM(damage_amount),0) FROM cases WHERE category='cyber'"),
        "total_indicators": one("SELECT COUNT(*) FROM indicators"),
    }
    conn.close()
    stats["cyber_links"] = len(get_all_link_pairs("cyber"))
    stats["physical_links"] = len(get_all_link_pairs("physical"))
    return stats


def get_top_reused_indicators(category, limit=8):
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.indicator_type, i.raw_value, COUNT(DISTINCT i.case_id) AS used
        FROM indicators i JOIN cases c ON i.case_id=c.case_id
        WHERE c.category=?
        GROUP BY i.indicator_type, i.norm_value
        HAVING used>1 ORDER BY used DESC LIMIT ?""", (category, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
