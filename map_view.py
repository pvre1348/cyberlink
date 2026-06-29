"""
map_view.py — สร้างแผนที่จริง (folium) สำหรับ 2 แผนผัง
  - build_cyber_map    : แผนผังไซเบอร์ (จุดคดี + เส้นเชื่อมโยง) ใช้ทำมวลชนสัมพันธ์
  - build_physical_map : แผนผังสายตรวจ (จุดเสี่ยง + จุดคดี + เส้นเชื่อมโยงข้ามพื้นที่)
"""
try:
    import folium
except Exception:        # ยังไม่ได้ติดตั้ง folium — ฟังก์ชันแผนที่จะถูกเรียกก็ต่อเมื่อมี folium เท่านั้น
    folium = None

LUMPHINI_CENTER = [13.7305, 100.5460]  # ศูนย์กลางแผนที่ (โดยประมาณ)

RISK_COLOR = {"สูง": "#D7263D", "ปานกลาง": "#F0A500", "ต่ำ": "#2E7D52"}

# สีไล่สำหรับขอบเขตแต่ละ สน. (สน.หลักใช้กรมท่าเข้ม)
AREA_COLORS = ["#2E86AB", "#A23B72", "#F18F01", "#3B8C6E", "#7B4B94", "#C0271A", "#1B998B"]
MAIN_COLOR = "#14233D"


def _centroid(poly):
    pts = poly[:-1] if len(poly) > 1 and poly[0] == poly[-1] else poly
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def _base_map(boundaries):
    """boundaries = list ของ dict {code,name,is_main,polygon} หรือ list ของ polygon (เก่า)"""
    m = folium.Map(location=LUMPHINI_CENTER, zoom_start=13, tiles="OpenStreetMap")
    ci = 0
    for area in boundaries:
        # รองรับทั้งรูปแบบใหม่ (dict) และเก่า (list พิกัด)
        if isinstance(area, dict):
            poly = area.get("polygon", [])
            code = area.get("code", "")
            is_main = area.get("is_main", 0)
        else:
            poly, code, is_main = area, "", 0
        if len(poly) < 3:
            continue
        if is_main:
            color = MAIN_COLOR
            weight = 3
        else:
            color = AREA_COLORS[ci % len(AREA_COLORS)]
            ci += 1
            weight = 2
        folium.Polygon(poly, color=color, weight=weight, fill=True, fill_color=color,
                       fill_opacity=0.10, tooltip=code).add_to(m)
        # ป้ายชื่อ สน. ที่จุดศูนย์กลางพื้นที่
        if code:
            c = _centroid(poly)
            folium.map.Marker(
                c, icon=folium.DivIcon(
                    html=f'<div style="font-family:sans-serif;font-size:11px;font-weight:600;'
                         f'color:{color};white-space:nowrap;text-shadow:0 0 3px #fff,0 0 3px #fff;">'
                         f'{code}</div>')).add_to(m)
    return m


def _add_stations(m, stations):
    for s in stations:
        if s.get("lat") is None or s.get("lng") is None:
            continue
        is_main = s.get("is_main")
        color = "#E0533D" if is_main else "#14233D"
        label = f'{s["code"]}'
        if s.get("direction"):
            label += f' ({s["direction"]})'
        folium.Marker(
            [s["lat"], s["lng"]],
            tooltip=label,
            icon=folium.Icon(color="red" if is_main else "darkblue", icon="home", prefix="fa"),
        ).add_to(m)


def build_cyber_map(stations, cases, pairs, boundary):
    m = _base_map(boundary)
    _add_stations(m, stations)
    by_id = {c["case_id"]: c for c in cases}

    # จุดคดีไซเบอร์
    for c in cases:
        if c.get("lat") is None or c.get("lng") is None:
            continue
        popup = f'{c["case_number"]} · {c["crime_type"]}<br>{c["station_code"]} · เสียหาย {c.get("damage_amount",0):,.0f} บ.'
        folium.CircleMarker([c["lat"], c["lng"]], radius=7, color="#25406B",
                            fill=True, fill_color="#25406B", fill_opacity=0.9,
                            tooltip=c["case_number"], popup=popup).add_to(m)

    # เส้นเชื่อมโยงคดี (สีส้ม = เส้นด้ายแดงโยงคดี)
    for a, b, n in pairs:
        ca, cb = by_id.get(a), by_id.get(b)
        if ca and cb and ca.get("lat") and cb.get("lat"):
            folium.PolyLine([[ca["lat"], ca["lng"]], [cb["lat"], cb["lng"]]],
                            color="#E0533D", weight=2 + n, opacity=0.8,
                            tooltip=f"{n} จุดร่วม").add_to(m)
    return m


def build_physical_map(stations, cases, risk_points, pairs, boundary):
    m = _base_map(boundary)
    _add_stations(m, stations)
    by_id = {c["case_id"]: c for c in cases}

    # จุดเสี่ยง (วงกลมสีตามระดับความเสี่ยง)
    for p in risk_points:
        col = RISK_COLOR.get(p["level"], "#F0A500")
        folium.Circle([p["lat"], p["lng"]], radius=180, color=col, weight=2,
                      fill=True, fill_color=col, fill_opacity=0.25,
                      tooltip=f'{p["name"]} · เสี่ยง{p["level"]}',
                      popup=p.get("note") or p["name"]).add_to(m)

    # จุดคดีในพื้นที่
    for c in cases:
        if c.get("lat") is None or c.get("lng") is None:
            continue
        sev = c.get("severity", 1) or 1
        popup = (f'{c["case_number"]} · {c["crime_type"]}<br>{c["station_code"]} · '
                 f'{c.get("time_bucket","")}<br>คนร้าย/รถ: {c.get("location_detail","")}')
        folium.CircleMarker([c["lat"], c["lng"]], radius=5 + sev * 2, color="#7A1F2B",
                            fill=True, fill_color="#B3434F", fill_opacity=0.85,
                            tooltip=c["case_number"], popup=popup).add_to(m)

    # เส้นเชื่อมโยงข้ามพื้นที่ (ทะเบียนรถ/ลักษณะคนร้ายตรงกัน)
    for a, b, n in pairs:
        ca, cb = by_id.get(a), by_id.get(b)
        if ca and cb and ca.get("lat") and cb.get("lat"):
            folium.PolyLine([[ca["lat"], ca["lng"]], [cb["lat"], cb["lng"]]],
                            color="#E0533D", weight=2 + n, opacity=0.85, dash_array="6",
                            tooltip=f"{n} จุดร่วม").add_to(m)
    return m


def simple_points_map(points, center=None):
    """แผนที่ง่าย ๆ สำหรับหน้าจัดการจุดเสี่ยง (โชว์จุดปัจจุบัน + ให้คลิกเพิ่ม)"""
    m = folium.Map(location=center or LUMPHINI_CENTER, zoom_start=14)
    for p in points:
        col = RISK_COLOR.get(p.get("level"), "#F0A500")
        folium.CircleMarker([p["lat"], p["lng"]], radius=8, color=col,
                            fill=True, fill_color=col, fill_opacity=0.7,
                            tooltip=p.get("name", "")).add_to(m)
    return m
