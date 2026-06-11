import os
import json
import re
import logging
from datetime import date
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ✅ Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

TOKEN = "(ซ่อน)"  
DATA_FILE = "counts.json"

# ================================
# File Management (Robust Load/Save)
# ================================

def load_data():
    """
    โหลดข้อมูล counts.json อย่างปลอดภัย
    ✅ ถ้าไฟล์ไม่มี → สร้างไฟล์ใหม่
    ✅ ถ้าไฟล์เสียหาย → คืนค่าว่างและบันทึก error
    ✅ ไม่ Crash → บอทยังทำงานต่อ
    """
    if not os.path.exists(DATA_FILE):
        logging.info(f"📁 ไฟล์ {DATA_FILE} ไม่มี สร้างใหม่")
        return {}
    
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logging.info(f"✅ โหลด {DATA_FILE} สำเร็จ")
            return data
    except json.JSONDecodeError as e:
        logging.error(f"❌ ไฟล์ JSON เสียหาย (JSONDecodeError): {e}")
        logging.warning("🔄 กำลังสร้างโครงสร้างใหม่...")
        return {}
    except IOError as e:
        logging.error(f"❌ ข้อผิดพลาดในการอ่านไฟล์: {e}")
        logging.warning("🔄 กำลังสร้างโครงสร้างใหม่...")
        return {}
    except Exception as e:
        logging.error(f"❌ ข้อผิดพลาดที่ไม่คาดคิด: {e}")
        return {}

def save_data(data):
    """
    บันทึกข้อมูลลง counts.json อย่างปลอดภัย
    ✅ ใช้ Context Manager
    ✅ Error Handling
    ✅ ไม่ Crash
    """
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info(f"✅ บันทึก {DATA_FILE} สำเร็จ")
    except IOError as e:
        logging.error(f"❌ บันทึกไฟล์ล้มเหลว (IOError): {e}")
    except Exception as e:
        logging.error(f"❌ บันทึกไฟล์ล้มเหลว (Exception): {e}")

# ================================
# Regular Expression & Validation
# ================================

# Regular Expression สำหรับหาแพทเทิร์น "ชื่อ/ตัวเลข" เช่น แบงค์/41
NAME_NUM_RE = re.compile(r'([^\s,\/:：]+)\s*[\/\\]\s*(\d+)', re.UNICODE)

def is_valid_input(name, num):
    """
    ✅ Fix #21: ตรวจสอบข้อมูลก่อนบันทึก
    
    ตรวจสอบ:
    - ชื่อ: ต้องไม่ว่างเปล่า
    - เลขงาน: ต้องเป็นตัวเลขเท่านั้นและมีความยาวไม่เกิน 5 หลัก
    """
    if not name or not name.strip():
        return False
    if not num.isdigit() or len(num) > 5:
        return False
    return True

# ================================
# Bot Command Handlers
# ================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """คำสั่ง /start"""
    await update.message.reply_text(
        "🤖 บอตบันทึกยอดส่งงานพร้อมใช้งานแล้วครับ!\n\n"
        "📌 รูปแบบการส่งงาน:\n"
        "พิมพ์ 'ชื่อ/เลขงาน' เรียงลงมาหลายบรรทัดได้เลยครับ\n\n"
        "📊 ตัวอย่าง:\n"
        "แบงค์/41\n"
        "สมาชิก/99\n"
        "ธนาคาร/2"
    )

async def handle_report_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    จัดการข้อความรายงาน
    ✅ Fix #17: รับเฉพาะ Text (ไม่รับ Caption)
    ✅ Fix #21: ตรวจสอบข้อมูลด้วย is_valid_input()
    """
    
    # ✅ Fix #17: ดึงเฉพาะ text (ไม่ต้อง caption)
    raw_text = (update.message.text or "").strip()
    
    if not raw_text:
        logging.debug("⚠️ ได้รับข้อความว่างเปล่า")
        return

    logging.info(f"📨 ได้รับข้อความ: {raw_text[:50]}...")

    # หาคู่ ชื่อ/ตัวเลข ทั้งหมดในข้อความ
    matches = NAME_NUM_RE.findall(raw_text)
    
    if not matches:
        logging.info("⚠️ ไม่พบแพทเทิร์น ชื่อ/ตัวเลข ในข้อความ")
        return

    logging.info(f"🔍 พบรูปแบบ: {matches}")

    data = load_data()
    today = date.today().isoformat()
    if today not in data:
        data[today] = {}

    parsed_summary = []
    valid_count = 0
    invalid_count = 0
    
    # แยกประเภท: ถ้ามีคำว่าแชทในข้อความให้เป็น chat ถ้าไม่มีให้เป็น comment
    job_type = "chat" if any(k in raw_text.lower() for k in ["แชท", "chat"]) else "comment"
    job_label = "ทักแชท" if job_type == "chat" else "ยิงคอมเมนต์"

    # วนลูปบันทึกยอดตามรายชื่อที่เจอ
    for name, num in matches:
        # ✅ Fix #21: ตรวจสอบข้อมูลก่อนบันทึก
        if is_valid_input(name, num):
            name = name.strip()
            
            if name not in data[today]:
                data[today][name] = {"chat": 0, "comment": 0}
                
            # บวกเพิ่มทีละ 1 แต้มต่อบรรทัด
            data[today][name][job_type] += 1
            parsed_summary.append(f"• {name} (งานที่ {num})")
            valid_count += 1
            logging.info(f"✅ บันทึก: {name}/{num} ({job_label})")
        else:
            # ปฏิเสธข้อมูลที่ไม่ถูกต้อง
            logging.warning(f"❌ ปฏิเสธข้อมูลที่ไม่ถูกต้อง: {name}/{num}")
            invalid_count += 1

    # บันทึกเฉพาะเมื่อมีข้อมูล valid
    if valid_count > 0:
        save_data(data)

        # ส่งข้อความตอบกลับสรุปรายการที่บันทึกสำเร็จ
        reply_msg = f"✅ บันทึกรายงาน [{job_label}] สำเร็จ ยอดรวม {valid_count} รายการ:\n" + "\n".join(parsed_summary)
        
        if invalid_count > 0:
            reply_msg += f"\n\n⚠️ ข้อมูล {invalid_count} รายการ ถูกปฏิเสธ เนื่องจากรูปแบบไม่ถูกต้อง"
        
        await update.message.reply_text(reply_msg)
    else:
        # ถ้าไม่มีข้อมูล valid เลย
        if invalid_count > 0:
            await update.message.reply_text(
                f"⚠️ ข้อมูล {invalid_count} รายการ ถูกปฏิเสธ\n\n"
                f"📝 เหตุผล:\n"
                f"• ชื่อไม่ควรว่างเปล่า\n"
                f"• เลขงานต้องเป็นตัวเลข และไม่เกิน 5 หลัก\n\n"
                f"📌 ตัวอย่างที่ถูก: แบงค์/41"
            )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """คำสั่ง /stats แสดงสรุปยอด"""
    data = load_data()
    today = date.today().isoformat()
    
    if today not in data or not data[today]:
        await update.message.reply_text("📊 วันนี้ยังไม่มีรายงานส่งงานเข้ามาครับ")
        return
        
    lines = [f"📊 สรุปยอดประจำวันที่ {today} 📊", "━" * 40]
    total_chat = 0
    total_comment = 0
    
    for name, stats in data[today].items():
        lines.append(f"👤 {name}")
        lines.append(f"   ทักแชท: {stats['chat']} รายการ | คอมเมนต์: {stats['comment']} รายการ")
        total_chat += stats['chat']
        total_comment += stats['comment']
        
    lines.append("━" * 40)
    lines.append(f"📈 ยอดรวมทั้งหมดวันนี้")
    lines.append(f"   🔵 ทักแชทสะสม: {total_chat} รายการ")
    lines.append(f"   🟢 คอมเมนต์สะสม: {total_comment} รายการ")
    
    await update.message.reply_text("\n".join(lines))

# ================================
# Main Bot Setup
# ================================

def main():
    app = Application.builder().token(TOKEN).build()
    
    # ลงทะเบียนคำสั่ง
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    
    # ✅ Fix #17: เปลี่ยน filters.TEXT() เป็น filters.TEXT
    # รับเฉพาะข้อความธรรมดา ไม่รับ Caption
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_report_text))
    
    logging.info("🚀 บอตกำลังรันระบบแยกข้อความรายงาน...")
    logging.info("📋 ฟีเจอร์ที่เปิดใช้:")
    logging.info("  ✅ Fix #17: Text-only filtering")
    logging.info("  ✅ Fix #21: Input validation")
    logging.info("  ✅ Error handling: Robust file management")
    
    app.run_polling()

if __name__ == "__main__":
    main()
