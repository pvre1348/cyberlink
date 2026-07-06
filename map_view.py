"""
map_view.py — สร้างแผนที่ (folium) และตรรกะจับกลุ่มพื้นที่เสี่ยงด้วยพิกัด

ส่วนสำคัญที่เพิ่มใหม่:
  - cluster_cases()    : จับกลุ่มจุดเกิดเหตุที่อยู่ใกล้กัน (union-find + haversine)
  - build_patrol_map() : แผนผังสายตรวจ = วงสีเสี่ยงอัตโนมัติ + จุดคดี + หมุดจุดเสี่ยง (ไม่มีเส้นเชื่อม)
  - build_linkage_map(): แผนที่เชื่อมโยงคดี = จุดคดี + เส้นเชื่อม (ไม่มีวงสี)
"""
import math

try:
    import folium
except Exception:
    folium = None

LUMPHINI_CENTER = [13.7305, 100.5460]

# สีวง/ป้ายตามระดับความเสี่ยง (เกณฑ์ตัวเลขตายตัว)
CLUSTER_COLOR = {"สูง": "#D7263D", "ปานกลาง": "#F0A500", "ต่ำ": "#2E7D52"}
# สีไอคอนหมุดจุดเสี่ยงที่บันทึกเอง (ชื่อสีของ folium Icon)
PIN_COLOR = {"สูง": "red", "ปานกลาง": "orange", "ต่ำ": "green"}

AREA_COLORS = ["#2E86AB", "#A23B72", "#F18F01", "#3B8C6E", "#7B4B94", "#C0271A", "#1B998B"]
MAIN_COLOR = "#14233D"


# ----------------------------------------------------------------------
# การจับกลุ่มพื้นที่เสี่ยงด้วยพิกัด (หัวใจของส่วนที่ 1)
# ----------------------------------------------------------------------
def _haversine_m(a, b):
    """ระยะทางจริงระหว่างพิกัด 2 จุด หน่วยเมตร (สูตร haversine)"""
    R = 6371000.0
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def cluster_level(count):
    """เกณฑ์ระดับความเสี่ยงจากจำนวนคดี: ≤3 ต่ำ(เขียว) / 4-5 กลาง(เหลือง) / >5 สูง(แดง)"""
    if count > 5:
        return "สูง"
    if count >= 4:
        return "ปานกลาง"
    return "ต่ำ"


def cluster_cases(cases, radius_m=400):
    """จับกลุ่มคดีที่จุดเกิดเหตุอยู่ใกล้กันภายในรัศมีที่กำหนด (ค่าเริ่มต้น 400 ม.)

    ใช้แนวคิด union-find: คดี 2 คดีอยู่กลุ่มเดียวกันถ้าห่างกัน <= radius_m
    (เชื่อมต่อเป็นลูกโซ่ได้ เช่น A ใกล้ B และ B ใกล้ C -> A B C วงเดียวกัน)
    คืนค่า list ของ cluster: {center, cases, count, radius_m}
    """
    pts = [c for c in cases if c.get("lat") is not None and c.get("lng") is not None]
    n = len(pts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_m((pts[i]["lat"], pts[i]["lng"]),
                             (pts[j]["lat"], pts[j]["lng"]))
            if d <= radius_m:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(pts[i])

    clusters = []
    for members in groups.values():
        lat = sum(m["lat"] for m in members) / len(members)
        lng = sum(m["lng"] for m in members) / len(members)
        spread = max((_haversine_m((lat, lng), (m["lat"], m["lng"])) for m in members),
                     default=0)
        clusters.append({
            "center": [lat, lng],
            "cases": members,
            "count": len(members),
            # รัศมีวงที่วาด = ระยะไกลสุดของสมาชิก + กันชน 100 ม. (ขั้นต่ำ 150 ม. ให้เห็นวง)
            "radius_m": max(150, spread + 100),
        })
    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters


# ----------------------------------------------------------------------
# ส่วนประกอบพื้นฐานของแผนที่
# ----------------------------------------------------------------------
def _centroid(poly):
    pts = poly[:-1] if len(poly) > 1 and poly[0] == poly[-1] else poly
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def _base_map(boundaries):
    m = folium.Map(location=LUMPHINI_CENTER, zoom_start=13, tiles="OpenStreetMap")
    ci = 0
    for area in boundaries:
        if isinstance(area, dict):
            poly = area.get("polygon", [])
            code = area.get("code", "")
            is_main = area.get("is_main", 0)
        else:
            poly, code, is_main = area, "", 0
        if len(poly) < 3:
            continue
        if is_main:
            color, weight = MAIN_COLOR, 3
        else:
            color = AREA_COLORS[ci % len(AREA_COLORS)]
            ci += 1
            weight = 2
        folium.Polygon(poly, color=color, weight=weight, fill=True, fill_color=color,
                       fill_opacity=0.10, tooltip=code).add_to(m)
        if code:
            c = _centroid(poly)
            folium.map.Marker(c, icon=folium.DivIcon(
                html=f'<div style="font-family:sans-serif;font-size:11px;font-weight:600;'
                     f'color:{color};white-space:nowrap;text-shadow:0 0 3px #fff,0 0 3px #fff;">'
                     f'{code}</div>')).add_to(m)
    return m


def _add_stations(m, stations):
    for s in stations:
        if s.get("lat") is None or s.get("lng") is None:
            continue
        is_main = s.get("is_main")
        label = f'{s["code"]}' + (f' ({s["direction"]})' if s.get("direction") else "")
        folium.Marker([s["lat"], s["lng"]], tooltip=label,
                      icon=folium.Icon(color="red" if is_main else "darkblue",
                                       icon="home", prefix="fa")).add_to(m)


def _add_case_dots(m, cases, color="#B3434F", edge="#7A1F2B"):
    for c in cases:
        if c.get("lat") is None or c.get("lng") is None:
            continue
        sev = c.get("severity", 1) or 1
        popup = (f'{c["case_number"]} · {c.get("crime_type","")}<br>'
                 f'{c.get("station_code","")} · {c.get("time_bucket","") or ""}')
        folium.CircleMarker([c["lat"], c["lng"]], radius=4 + sev, color=edge,
                            fill=True, fill_color=color, fill_opacity=0.9,
                            tooltip=c["case_number"], popup=popup).add_to(m)


# ----------------------------------------------------------------------
# แผนที่ 1: แผนผังสายตรวจ (วงสีเสี่ยงอัตโนมัติ + จุดคดี + หมุดจุดเสี่ยง — ไม่มีเส้นเชื่อม)
# ----------------------------------------------------------------------
def build_patrol_map(stations, cases, clusters, risk_points, boundaries):
    m = _base_map(boundaries)
    _add_stations(m, stations)

    # วงพื้นที่เสี่ยงจากการจับกลุ่มอัตโนมัติ
    for cl in clusters:
        lv = cluster_level(cl["count"])
        col = CLUSTER_COLOR[lv]
        nums = ", ".join(c["case_number"] for c in cl["cases"][:8])
        more = "" if cl["count"] <= 8 else f" และอีก {cl['count'] - 8} คดี"
        folium.Circle(cl["center"], radius=cl["radius_m"], color=col, weight=2,
                      fill=True, fill_color=col, fill_opacity=0.22,
                      tooltip=f'{cl["count"]} คดี · เสี่ยง{lv}',
                      popup=f'คดีในกลุ่ม: {nums}{more}').add_to(m)

    # จุดคดีรายจุด
    _add_case_dots(m, cases)

    # หมุดจุดเสี่ยงที่เจ้าหน้าที่บันทึกเอง (แสดงคู่กัน ไม่ลบทิ้ง)
    for p in risk_points:
        icon_col = PIN_COLOR.get(p.get("level"), "orange")
        folium.Marker([p["lat"], p["lng"]],
                      tooltip=f'จุดเสี่ยง (บันทึกเอง): {p["name"]} · {p.get("level","")}',
                      popup=p.get("note") or p["name"],
                      icon=folium.Icon(color=icon_col, icon="exclamation-triangle",
                                       prefix="fa")).add_to(m)
    return m


# ----------------------------------------------------------------------
# แผนที่ 2: แผนที่เชื่อมโยงคดี (จุดคดี + เส้นเชื่อม — ไม่มีวงสี)
# ----------------------------------------------------------------------
def build_linkage_map(stations, cases, pairs, boundaries, dot_color="#25406B"):
    m = _base_map(boundaries)
    _add_stations(m, stations)
    _add_case_dots(m, cases, color=dot_color, edge=dot_color)
    by_id = {c["case_id"]: c for c in cases}
    for a, b, n in pairs:
        ca, cb = by_id.get(a), by_id.get(b)
        if ca and cb and ca.get("lat") and cb.get("lat"):
            folium.PolyLine([[ca["lat"], ca["lng"]], [cb["lat"], cb["lng"]]],
                            color="#E0533D", weight=2 + n, opacity=0.85,
                            tooltip=f"{n} จุดร่วม").add_to(m)
    return m


# ----------------------------------------------------------------------
# แผนที่คดีออนไลน์ (จุดคดีอย่างเดียว — เส้นเชื่อมย้ายไปหน้าเชื่อมโยงคดี)
# ----------------------------------------------------------------------
def build_cyber_map(stations, cases, pairs, boundaries):
    m = _base_map(boundaries)
    _add_stations(m, stations)
    for c in cases:
        if c.get("lat") is None or c.get("lng") is None:
            continue
        popup = (f'{c["case_number"]} · {c["crime_type"]}<br>{c["station_code"]} · '
                 f'เสียหาย {c.get("damage_amount", 0):,.0f} บ.')
        folium.CircleMarker([c["lat"], c["lng"]], radius=7, color="#25406B",
                            fill=True, fill_color="#25406B", fill_opacity=0.9,
                            tooltip=c["case_number"], popup=popup).add_to(m)
    # เส้นเชื่อม (วาดเฉพาะเมื่อส่ง pairs มา — หน้าออนไลน์ส่ง [] จึงไม่มีเส้น)
    by_id = {c["case_id"]: c for c in cases}
    for a, b, n in pairs:
        ca, cb = by_id.get(a), by_id.get(b)
        if ca and cb and ca.get("lat") and cb.get("lat"):
            folium.PolyLine([[ca["lat"], ca["lng"]], [cb["lat"], cb["lng"]]],
                            color="#E0533D", weight=2 + n, opacity=0.8,
                            tooltip=f"{n} จุดร่วม").add_to(m)
    return m


# ----------------------------------------------------------------------
# แผนที่เลือกตำแหน่ง (ปักหมุดในฟอร์มบันทึกคดี) — คงเดิม
# ----------------------------------------------------------------------
def pick_location_map(boundaries, current_lat=None, current_lng=None):
    m = _base_map(boundaries)
    if current_lat is not None and current_lng is not None:
        folium.Marker([current_lat, current_lng],
                      tooltip="ตำแหน่งปัจจุบัน (คลิกที่อื่นเพื่อย้าย)",
                      icon=folium.Icon(color="red", icon="map-pin", prefix="fa")).add_to(m)
    return m


def simple_points_map(points, center=None):
    m = folium.Map(location=center or LUMPHINI_CENTER, zoom_start=14)
    for p in points:
        col = CLUSTER_COLOR.get(p.get("level"), "#F0A500")
        folium.CircleMarker([p["lat"], p["lng"]], radius=8, color=col,
                            fill=True, fill_color=col, fill_opacity=0.7,
                            tooltip=p.get("name", "")).add_to(m)
    return m
