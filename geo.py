"""
geo.py — อ่านไฟล์ขอบเขตพื้นที่ แล้วแปลงเป็น list ของ polygon [[lat,lng],...]
รองรับ .geojson / .json / .kml / .kmz (ไฟล์ที่ export จาก Google My Maps)

ใช้ความรู้: การอ่านไฟล์, การแยกวิเคราะห์ข้อความ (parsing), list/loop
"""
import json
import zipfile
import io
import xml.etree.ElementTree as ET


def _from_geojson(text):
    """ดึง polygon จาก GeoJSON (พิกัดใน GeoJSON เป็น [lng,lat] ต้องสลับ)"""
    data = json.loads(text)
    polygons = []

    def handle_geometry(geom):
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])
        if gtype == "Polygon":
            ring = coords[0] if coords else []
            polygons.append([[pt[1], pt[0]] for pt in ring])
        elif gtype == "MultiPolygon":
            for poly in coords:
                ring = poly[0] if poly else []
                polygons.append([[pt[1], pt[0]] for pt in ring])

    if data.get("type") == "FeatureCollection":
        for feat in data.get("features", []):
            if feat.get("geometry"):
                handle_geometry(feat["geometry"])
    elif data.get("type") == "Feature":
        handle_geometry(data["geometry"])
    else:
        handle_geometry(data)
    return polygons


def _from_kml(text):
    """ดึง polygon จาก KML (พิกัดเป็น 'lng,lat,alt' คั่นด้วยช่องว่าง)"""
    polygons = []
    # ตัด namespace ออกเพื่อให้ค้นหา tag ง่าย
    text = text.replace('xmlns="http://www.opengis.net/kml/2.2"', "")
    root = ET.fromstring(text)
    for coord_el in root.iter("coordinates"):
        ring = []
        for token in coord_el.text.strip().split():
            parts = token.split(",")
            if len(parts) >= 2:
                lng, lat = float(parts[0]), float(parts[1])
                ring.append([lat, lng])
        if len(ring) >= 3:
            polygons.append(ring)
    return polygons


def parse_boundary_file(filename, file_bytes):
    """รับชื่อไฟล์ + ข้อมูล bytes -> คืน list ของ polygon"""
    name = filename.lower()
    if name.endswith((".geojson", ".json")):
        return _from_geojson(file_bytes.decode("utf-8"))
    if name.endswith(".kml"):
        return _from_kml(file_bytes.decode("utf-8"))
    if name.endswith(".kmz"):
        # KMZ คือไฟล์ zip ที่ข้างในมี doc.kml
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
            if kml_name:
                return _from_kml(z.read(kml_name).decode("utf-8"))
    return []


def _named_from_kml(text):
    """อ่านขอบเขตจาก KML พร้อมชื่อจาก <Placemark><name> -> [{name, polygon}, ...]"""
    text = text.replace('xmlns="http://www.opengis.net/kml/2.2"', "")
    root = ET.fromstring(text)
    areas = []
    for pm in root.iter("Placemark"):
        name_el = pm.find("name")
        nm = name_el.text.strip() if (name_el is not None and name_el.text) else ""
        for coord_el in pm.iter("coordinates"):
            ring = []
            for token in coord_el.text.strip().split():
                parts = token.split(",")
                if len(parts) >= 2:
                    ring.append([float(parts[1]), float(parts[0])])
            if len(ring) >= 3:
                areas.append({"name": nm, "polygon": ring})
    return areas


def parse_named_boundaries(filename, file_bytes):
    """คืนรายการขอบเขตแบบมีชื่อ [{name, polygon}, ...] รองรับ kml/kmz/geojson"""
    name = filename.lower()
    if name.endswith(".kml"):
        return _named_from_kml(file_bytes.decode("utf-8"))
    if name.endswith(".kmz"):
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
            if kml_name:
                return _named_from_kml(z.read(kml_name).decode("utf-8"))
    # geojson: ไม่มีชื่อรายอัน -> ใส่ชื่อว่าง
    return [{"name": "", "polygon": p} for p in parse_boundary_file(filename, file_bytes)]
