@echo off
cd /d "%~dp0"
echo กำลังเปิดแอป... อย่าปิดหน้าต่างนี้ขณะใช้งาน
python -m streamlit run app.py
pause