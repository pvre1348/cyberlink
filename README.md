# CyberLink — ระบบคดีและพื้นที่เสี่ยง (Supabase + ระบบล็อกอิน)

โปรเจกต์วิชา 341314 Computer Programming · พื้นที่ สน.ลุมพินี และเขตติดต่อ

## ความสามารถ
- บันทึกคดี 2 กลุ่ม: **ออนไลน์** (บัญชี/ไลน์/เบอร์) และ **ในพื้นที่** (ทะเบียนรถ/ลักษณะคนร้าย)
- เชื่อมโยงคดีข้ามพื้นที่อัตโนมัติผ่าน "จุดร่วม"
- แผนที่จริง 2 แผนผัง (มวลชนสัมพันธ์ / สายตรวจ) + ปักหมุดจากแผนที่
- ระบบล็อกอิน (admin/user) สมัครด้วย invite code จำกัด 20 บัญชี
- ข้อมูลบน Supabase → ทุกอุปกรณ์เห็นชุดเดียวกัน

## ไฟล์
| ไฟล์ | หน้าที่ |
|------|---------|
| `app.py` | หน้าจอทั้งหมด (Streamlit) + ระบบล็อกอิน + คุมสิทธิ์ |
| `supa.py` | เชื่อมต่อ Supabase (อ่านค่าจาก secrets) |
| `auth.py` | ล็อกอิน/สมัคร/invite code/จัดการผู้ใช้ |
| `database.py` | อ่าน/เขียนข้อมูล + ตรรกะเชื่อมโยงคดี |
| `geo.py` | อ่านไฟล์ขอบเขต KML/GeoJSON |
| `map_view.py` | สร้างแผนที่ (folium) |
| `seed_data.py` | โครงพื้นฐาน + โหลด/ล้างข้อมูลตัวอย่าง |
| `.streamlit/config.toml` | ธีมมืด Esri |
| `.streamlit/secrets.toml` | คีย์ Supabase (สร้างเอง ไม่ push) |

## ติดตั้งครั้งแรก
1. รัน `supabase_setup.sql` ใน Supabase SQL Editor (สร้างตาราง)
2. สร้าง `.streamlit/secrets.toml` ใส่ค่า SUPABASE_URL / ANON_KEY / SERVICE_KEY
3. ติดตั้งไลบรารีและรัน:
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Deploy บน Streamlit Cloud
push ขึ้น GitHub → share.streamlit.io → Create app → ใส่ค่า secrets 3 ตัวในเมนู Secrets
(อย่า push ไฟล์ secrets.toml — .gitignore กันไว้แล้ว)

## ข้อจำกัด (เขียนในรายงาน)
ข้อมูลอยู่บน Supabase (สิงคโปร์) เหมาะกับ demo/ข้อมูลสมมติ
หากใช้จริงควรโฮสต์บนเซิร์ฟเวอร์ในประเทศเพื่อให้เป็นไปตาม PDPA และ พ.ร.บ.คอมพิวเตอร์
