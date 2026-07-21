# Roblox TD Macro

เครื่องมือ automation สำหรับเกม tower defense บน Roblox (Windows only)

สถานะปัจจุบัน: **Phase 1 + 2 เสร็จแล้ว** — window manager, control panel, stage editor

---

## ติดตั้ง

```bat
cd roblox_td_macro
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

ถ้าจะใช้ OCR (Phase 3) ต้องลง Tesseract แยกด้วย:
https://github.com/UB-Mannheim/tesseract/wiki

---

## รัน

**วิธีที่ 1 — ดับเบิลคลิก `run.bat`** (แนะนำ)

ครั้งแรกจะสร้าง venv + ลง dependency ให้เอง ใช้เวลาสักพัก ครั้งต่อไปเปิดทันที

**วิธีที่ 2 — สั่งเอง**

```bat
python main.py
```

จะมีแผงสองอันโผล่มา ลากย้ายได้ด้วยการคลิกค้างที่พื้นหลังแผง

---

## สร้าง run.exe

ดับเบิลคลิก **`build.bat`** รอ 3-8 นาที จะได้ `dist\run\run.exe`

ต้องเอาโฟลเดอร์ `dist\run` ไปทั้งอัน ไม่ใช่แค่ไฟล์ exe เพราะ Qt DLL อยู่ในนั้น

ข้อควรทราบ:

- ขนาดราว 180-250 MB เพราะ PySide6 + OpenCV
- Windows Defender อาจแจ้งเตือน false positive — เป็นเรื่องปกติของ PyInstaller ที่ไม่ได้เซ็น certificate ให้ add exclusion
- `config.yaml` และโฟลเดอร์ `profiles` จะอยู่ข้าง exe แก้ไขได้โดยไม่ต้อง build ใหม่
- ถ้าเปิดแล้วปิดทันทีไม่มี error ให้แก้ `run.spec` เป็น `console=True` แล้ว build ใหม่ จะเห็น traceback

---

## ขั้นตอนใช้งาน

1. เปิด Roblox แล้วเข้าเกม
2. กด **Attach + center window** — โปรแกรมจะย่อหน้าต่าง Roblox ให้ client area เป็น 1280×720 พอดี แล้วจัดกลางจอ แผงควบคุมจะไปเกาะซ้าย-ขวาอัตโนมัติ
3. เข้า stage ที่ต้องการ ใช้ teleport to spawn ของเกม แล้วปรับกล้องให้เข้าที่
4. กด **Open stage editor** → ตั้งชื่อ stage → กด **Capture ref** โปรแกรมจะเซฟภาพหน้าจอเป็น reference
5. คลิกบนภาพเพื่อปักหมุด แต่ละหมุดตั้งค่าได้:
   - **Action**: place / upgrade / sell / ability / wait
   - **Slot**: ช่องยูนิตบน hotbar (สำหรับ place)
   - **Times**: จำนวนครั้งที่กด upgrade
   - **Target step**: หมุด upgrade อ้างอิงหมุด place ตัวไหน
   - **Wait for**: เงื่อนไขก่อนทำ — cash / wave / delay
6. ลากหมุดบนภาพเพื่อขยับตำแหน่งได้ ค่าพิกัดอัปเดตอัตโนมัติ
7. กด **Save** → ได้ไฟล์ `profiles/xxx.json`

---

## ตั้งค่าในเกมก่อนใช้ (สำคัญมาก)

ถ้าเปลี่ยนค่าพวกนี้ทีหลัง profile ที่ทำไว้จะพังทันที

- Camera Mode: **Classic**
- Movement Mode: **Keyboard**
- Shift Lock Switch: **ปิด**
- Graphics Quality: ล็อกไว้ ห้ามเปลี่ยน
- Full screen: **ปิด** (ต้องเป็น windowed เท่านั้น)

---

## โครงสร้าง

```
core/window.py        หา + จัดตำแหน่งหน้าต่าง Roblox
core/input_driver.py  SendInput สำหรับ mouse/keyboard/scroll/drag
vision/capture.py     mss capture + template matching
data/profile.py       โมเดล stage profile + save/load JSON
ui/panels.py          แผงควบคุมซ้าย + แผงสถานะขวา
ui/stage_editor.py    หน้าปักหมุดบนภาพ stage
main.py               จุดเริ่ม
config.yaml           ตั้งค่าทั้งหมด
```

---

## ยังไม่ได้ทำ

| Phase | เนื้อหา |
|---|---|
| 2.5 | Teleport + camera normalize + ref image verify |
| 3 | Executor — OCR gating, place/upgrade, post-place verify |
| 4 | Win/loss detector + auto restart |
| 5 | SQLite stats + Discord webhook |

---

## ข้อควรทราบ

Roblox Terms of Use ห้าม automation ในระดับแพลตฟอร์ม การอนุญาตจากเจ้าของเกมไม่ครอบคลุมข้อนี้ ความเสี่ยงบัญชีเป็นของผู้ใช้เอง แนะนำให้ใช้ alt account
