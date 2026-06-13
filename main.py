import os
import time
import logging
import threading
import psycopg2
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ['TOKEN']
DATABASE_URL = os.environ['DATABASE_URL']
TH_TZ = ZoneInfo("Asia/Bangkok")
KEEP_ALIVE_PORT = 8099

CALC_AMOUNT, CALC_TYPE = range(2)
ADD_SCRIPT_TEXT, ADD_CLIP_TITLE, ADD_CLIP_URL = range(3)

FEE_ACCOUNT = 0.35
FEE_SYSTEM  = 0.05
COM_FAN     = 0.30
COM_STAFF   = 0.13

BTN_CHECKIN  = "✅ เช็คอินสู้ตาย!"
BTN_CHECKOUT = "🔴 เลิกงานแล้วน้า"
BTN_BREAK    = "☕ พักเติมพลัง"
BTN_RETURN   = "🔙 กลับมาลุยต่อ"
BTN_CALC     = "💰 คำนวณค่าคอมฯ"
BTN_SCRIPTS  = "📖 คลังสคริปต์"
BTN_CLIPS    = "📺 คลิปเตือนภัย จุ๊บๆ"
BTN_FAN      = "👫 ลูกค้าของแฟน (30%)"
BTN_STAFF    = "👔 ลูกค้าของพนักงาน (13%)"
BTN_CANCEL   = "🙅‍♀️ ยกเลิกก่อนนะ"


class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write("Anyong is alive 🍑".encode())

    def log_message(self, format, *args):
        pass


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


def run_keep_alive():
    server = ReusableHTTPServer(("0.0.0.0", KEEP_ALIVE_PORT), KeepAliveHandler)
    logger.info(f"Keep-alive server running on port {KEEP_ALIVE_PORT}")
    server.serve_forever()


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_CHECKIN,  BTN_CHECKOUT],
        [BTN_BREAK,    BTN_RETURN],
        [BTN_CALC,     BTN_SCRIPTS],
        [BTN_CLIPS],
    ],
    resize_keyboard=True,
)

TYPE_KEYBOARD = ReplyKeyboardMarkup(
    [
        [BTN_FAN, BTN_STAFF],
        [BTN_CANCEL],
    ],
    resize_keyboard=True,
)

CHECKIN_REPLIES = [
    "อันยองมาแล้วววว🍑 วันนี้สู้ๆนะคะ เช็คอินให้แล้วจ้า จุ๊บม๊วฟ~ ✨",
    "อ้าวมาแล้วเหรอคะ เก่งมากเลย🍑 อันยองจดไว้ให้แล้วนะคะ วันนี้ต้องปังๆค่า!",
    "เข้างานแล้วค่ะ🍑 อันยองจดไว้ให้แล้วนะ สู้สู้! อันยองเชียร์อยู่นะคะ 🎀",
    "มาทำงานแล้วเหรอ เยี่ยมเลยค่ะ🍑 บันทึกเรียบร้อยแล้วจ้า ทำดีๆนะคะ วันนี้ต้องสว่างมากเลย~",
]

CHECKOUT_REPLIES = [
    "เลิกงานแล้วเหรอคะ🍑 วันนี้เหนื่อยมั้ยคะ พักผ่อนเยอะๆนะ อันยองบันทึกไว้ให้แล้วจ้า 💖",
    "หมดวันแล้วววว🍑 อันยองจดให้เรียบร้อยค่า พรุ่งนี้เจอกันอีกนะคะ สู้ๆ!",
    "กลับบ้านได้แล้วค่ะ🍑 วันนี้ทำงานหนักมากเลย ขอบคุณที่ทุ่มเทนะคะ จุ๊บม๊วฟ~",
    "อันยองบันทึกเวลาเลิกงานไว้แล้วนะคะ🍑 คืนนี้นอนหลับพักผ่อนเยอะๆด้วยนะ ฝันดีค่า 🌙",
]

BREAK_REPLIES = [
    "พักกลางวันแล้วค่ะ🍑 กินข้าวให้อร่อยนะคะ ชาร์จพลังให้เต็มเลย อันยองบันทึกไว้ให้แล้วจ้า~",
    "หิวข้าวเหรอคะ🍑 ไปกินได้เลยนะ อันยองบันทึกไว้ให้เรียบร้อยแล้วค่า ☕",
    "พักก่อนนะคะ🍑 อาหารอร่อยๆช่วยให้สมองปลอดโปร่งเลยค่า บันทึกแล้วจ้า กลับมาลุยต่อนะ!",
]

RETURN_REPLIES = [
    "กลับมาแล้วเหรอคะ🍑 อิ่มข้าวแล้วก็มาลุยต่อเลย อันยองเชียร์อยู่นะ บันทึกแล้วจ้า 🔥",
    "ชาร์จพลังเสร็จแล้วก็มาสู้ต่อเลยค่ะ🍑 อันยองบันทึกไว้ให้แล้วนะ วันนี้ต้องปังมากๆ~",
    "กลับจากพักแล้วค่า🍑 พร้อมลุยแล้วใช่มั้ยคะ อันยองเชียร์อยู่ตลอดเลยนะ บันทึกแล้วจ้า ✨",
]

DEFAULT_REPLIES = [
    "อันยองจดไว้ให้เรียบร้อยแล้วนะคะ🍑 มีอะไรให้ช่วยอีกบอกได้เลยนะคะ จุ๊บม๊วฟ~",
    "โอเคค่ะ🍑 บันทึกไว้ให้แล้วจ้า อันยองอยู่ตรงนี้เสมอนะคะ 💖",
    "รับทราบแล้วค่า🍑 จดเรียบร้อยเลย สู้ๆนะคะ วันนี้ต้องโกยๆๆ! 🔥",
]

MANUAL = (
    "อันยองค่าาา! น้องอันยอง🍑 มาแล้วววว ✨\n\n"
    "วันนี้มีอะไรให้เค้าช่วยมั้ยคะ? กดปุ่มข้างล่างได้เลยนะ จุ๊บม๊วฟ! 🍑💖\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📖 *คู่มือการใช้งาน*\n\n"
    "✅ *เช็คอินสู้ตาย!*\n"
    "   → กดเมื่อมาถึงที่ทำงาน บันทึกเวลาเข้างาน\n\n"
    "🔴 *เลิกงานแล้วน้า*\n"
    "   → กดเมื่อเลิกงาน บันทึกเวลาออกงาน\n\n"
    "☕ *พักเติมพลัง*\n"
    "   → กดตอนออกไปพักกลางวัน\n\n"
    "🔙 *กลับมาลุยต่อ*\n"
    "   → กดตอนกลับจากพัก พร้อมทำงานต่อ\n\n"
    "💰 *คำนวณค่าคอมฯ*\n"
    "   → คำนวณค่าคอมมิชชั่น แยกตามประเภทลูกค้า\n\n"
    "📖 *คลังสคริปต์*\n"
    "   → ดูสคริปต์ปิดการขายสุดปัง 🔥\n\n"
    "📺 *คลิปเตือนภัย จุ๊บๆ*\n"
    "   → คลิปเตือนภัยมิจฉาชีพ ดูแล้วระวังตัวด้วยนะ!\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💡 หรือพิมพ์ข้อความอะไรก็ได้ อันยองจดให้เองเลยค่า\n"
    "สู้ๆนะคะทุกคน อันยองเชียร์อยู่นะ! 🍑"
)


def get_reply(replies: list, index: int) -> str:
    return replies[index % len(replies)]


def fmt(n: float) -> str:
    return f"{n:,.2f}"


def calc_commission(amount: float, rate: float) -> dict:
    fee_acc    = amount * FEE_ACCOUNT
    after_acc  = amount - fee_acc
    fee_sys    = after_acc * FEE_SYSTEM
    after_sys  = after_acc - fee_sys
    commission = after_sys * rate
    return {
        "amount":     amount,
        "rate":       rate,
        "fee_acc":    fee_acc,
        "after_acc":  after_acc,
        "fee_sys":    fee_sys,
        "after_sys":  after_sys,
        "commission": commission,
    }


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS work_logs (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    user_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    logged_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scripts (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    added_by BIGINT NOT NULL,
                    added_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS clips (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    added_by BIGINT NOT NULL,
                    added_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
    logger.info("Database initialised")


# ── Start / Help ──────────────────────────────────────────────────────────────

async def anyong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        MANUAL,
        reply_markup=MAIN_KEYBOARD,
        parse_mode="Markdown",
    )


# ── Commission conversation ───────────────────────────────────────────────────

async def calc_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 อันยองช่วยคิดค่าคอมให้นะคะ🍑\n\n"
        "พิมพ์ยอดเงิน (ตัวเลขเท่านั้นนะคะ) เลยค่า เช่น  300000",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CALC_AMOUNT


async def calc_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace(",", "").replace(" ", "")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "🍑 อ๊ะ~ ใส่ตัวเลขด้วยนะคะ เช่น 300000 แล้วลองใหม่ได้เลยค่า"
        )
        return CALC_AMOUNT

    context.user_data["calc_amount"] = amount
    await update.message.reply_text(
        f"ยอดเงิน {fmt(amount)} บาท รับทราบแล้วค่ะ🍑\n\n"
        "ลูกค้าคนนี้เป็นลูกค้าของใครคะ~?",
        reply_markup=TYPE_KEYBOARD,
    )
    return CALC_TYPE


async def calc_get_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == BTN_CANCEL:
        await update.message.reply_text(
            "โอเคค่ะ🍑 ยกเลิกแล้วนะคะ กลับมาคิดใหม่ได้ตลอดเลยนะ~",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    if "แฟน" in text:
        rate  = COM_FAN
        label = "ลูกค้าของแฟน"
    elif "พนักงาน" in text:
        rate  = COM_STAFF
        label = "ลูกค้าของพนักงาน"
    else:
        await update.message.reply_text("🍑 กรุณาเลือกจากปุ่มด้านล่างเลยนะคะ~")
        return CALC_TYPE

    amount = context.user_data["calc_amount"]
    c = calc_commission(amount, rate)

    result = (
        f"🍑 สรุปค่าคอมนะคะ~\n"
        f"{'─' * 30}\n"
        f"📌 ประเภท         : {label}\n"
        f"💵 ยอดเงินเต็ม    : {fmt(c['amount'])} บาท\n"
        f"{'─' * 30}\n"
        f"➖ ค่าบัญชี (35%) : {fmt(c['fee_acc'])} บาท\n"
        f"   เหลือ           : {fmt(c['after_acc'])} บาท\n"
        f"➖ ค่าระบบ  (5%)  : {fmt(c['fee_sys'])} บาท\n"
        f"   เหลือ           : {fmt(c['after_sys'])} บาท\n"
        f"{'─' * 30}\n"
        f"✅ ค่าคอม ({int(rate*100)}%)    : {fmt(c['commission'])} บาท 🎉\n\n"
        f"สู้ๆนะคะ อันยองเชียร์อยู่! 🍑🔥"
    )

    await update.message.reply_text(result, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


async def calc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ยกเลิกแล้วค่ะ🍑 กลับเมนูหลักแล้วนะ~",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ── Scripts ───────────────────────────────────────────────────────────────────

async def menu_scripts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title FROM scripts ORDER BY added_at DESC")
            rows = cur.fetchall()

    if not rows:
        await update.message.reply_text(
            "📖 ยังไม่มีสคริปต์ในคลังเลยค่ะ🍑\n\n"
            "แอดมินสามารถเพิ่มสคริปต์ได้ด้วยคำสั่ง /addscript นะคะ 💖",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"📄 {row[1]}", callback_data=f"script_{row[0]}")]
        for row in rows
    ]
    await update.message.reply_text(
        "📖 คลังสคริปต์สุดปัง เลือกที่ชอบแล้วไปปิดการขายให้ยอดพุ่งเลยค่ะ! 🍑🔥",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def script_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    script_id = int(query.data.split("_")[1])

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT title, body FROM scripts WHERE id = %s", (script_id,))
            row = cur.fetchone()

    if not row:
        await query.message.reply_text("🍑 ขอโทษนะคะ ไม่พบสคริปต์นี้แล้วค่า")
        return

    title, body = row
    await query.message.reply_text(
        f"📄 *{title}*\n\n{body}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "ไปปิดการขายให้ยอดพุ่งนะคะ อันยองเชียร์อยู่! 🍑🔥",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


async def add_script_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 เพิ่มสคริปต์ใหม่เลยค่า🍑\n\n"
        "พิมพ์ *หัวข้อ | เนื้อหา* มาได้เลยนะคะ\n"
        "ตัวอย่าง: เปิดบทสนทนา | สวัสดีค่ะ ขอแนะนำโปรฯ ดีๆ...\n\n"
        "หรือพิมพ์ /cancel เพื่อยกเลิกนะคะ",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADD_SCRIPT_TEXT


async def add_script_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "|" not in text:
        await update.message.reply_text(
            "🍑 ขอรูปแบบ *หัวข้อ | เนื้อหา* ด้วยนะคะ แล้วลองใหม่ได้เลย~",
            parse_mode="Markdown",
        )
        return ADD_SCRIPT_TEXT

    parts = text.split("|", 1)
    title = parts[0].strip()
    body  = parts[1].strip()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scripts (title, body, added_by) VALUES (%s, %s, %s)",
                (title, body, update.message.from_user.id),
            )
        conn.commit()

    await update.message.reply_text(
        f"✅ เพิ่มสคริปต์ *{title}* เรียบร้อยแล้วค่า🍑 ปังมากเลยนะ! 🔥",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


async def del_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "🍑 ใช้คำสั่ง /delscript [id] นะคะ เช่น /delscript 1",
            reply_markup=MAIN_KEYBOARD,
        )
        return
    script_id = int(args[0])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scripts WHERE id = %s", (script_id,))
        conn.commit()
    await update.message.reply_text(
        f"🗑️ ลบสคริปต์ #{script_id} เรียบร้อยแล้วค่า🍑",
        reply_markup=MAIN_KEYBOARD,
    )


# ── Clips ─────────────────────────────────────────────────────────────────────

async def menu_clips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT title, url FROM clips ORDER BY added_at DESC")
            rows = cur.fetchall()

    if not rows:
        await update.message.reply_text(
            "📺 ยังไม่มีคลิปเตือนภัยในคลังเลยค่ะ🍑\n\n"
            "แอดมินสามารถเพิ่มได้ด้วยคำสั่ง /addclip นะคะ 💖",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    msg = "📺 *คลิปเตือนภัยมิจฉาชีพที่อันยองหามาให้ค่า:*\n\n"
    for i, (title, url) in enumerate(rows, 1):
        msg += f"{i}. [{title}]({url})\n"
    msg += "\nดูแล้วระวังตัวกันด้วยนะคะ เป็นห่วงน้าาา จุ๊บๆ 🍑💕"

    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        disable_web_page_preview=False,
        reply_markup=MAIN_KEYBOARD,
    )


async def add_clip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📺 เพิ่มคลิปเตือนภัยใหม่เลยค่า🍑\n\n"
        "พิมพ์ *ชื่อคลิป | ลิงก์* มาได้เลยนะคะ\n"
        "ตัวอย่าง: สแกมเมอร์หลอกโอน | https://youtu.be/xxx\n\n"
        "หรือพิมพ์ /cancel เพื่อยกเลิกนะคะ",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADD_CLIP_TITLE


async def add_clip_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "|" not in text:
        await update.message.reply_text(
            "🍑 ขอรูปแบบ *ชื่อคลิป | ลิงก์* ด้วยนะคะ แล้วลองใหม่ได้เลย~",
            parse_mode="Markdown",
        )
        return ADD_CLIP_TITLE

    parts = text.split("|", 1)
    title = parts[0].strip()
    url   = parts[1].strip()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clips (title, url, added_by) VALUES (%s, %s, %s)",
                (title, url, update.message.from_user.id),
            )
        conn.commit()

    await update.message.reply_text(
        f"✅ เพิ่มคลิป *{title}* เรียบร้อยแล้วค่า🍑 ขอบคุณที่แชร์นะคะ 💖",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


async def del_clip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "🍑 ใช้คำสั่ง /delclip [id] นะคะ เช่น /delclip 1",
            reply_markup=MAIN_KEYBOARD,
        )
        return
    clip_id = int(args[0])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM clips WHERE id = %s", (clip_id,))
        conn.commit()
    await update.message.reply_text(
        f"🗑️ ลบคลิป #{clip_id} เรียบร้อยแล้วค่า🍑",
        reply_markup=MAIN_KEYBOARD,
    )


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ยกเลิกแล้วค่ะ🍑 กลับเมนูหลักแล้วนะ~",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ── Work log handlers ─────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = update.message.text.strip()
    now  = datetime.now(TH_TZ)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    seed = user.id + int(now.timestamp())

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO work_logs (user_id, user_name, action, logged_at) VALUES (%s, %s, %s, %s)",
                (user.id, user.full_name, text, now),
            )
        conn.commit()

    if text == BTN_CHECKIN:
        reply = get_reply(CHECKIN_REPLIES, seed)
    elif text == BTN_CHECKOUT:
        reply = get_reply(CHECKOUT_REPLIES, seed)
    elif text == BTN_BREAK:
        reply = get_reply(BREAK_REPLIES, seed)
    elif text == BTN_RETURN:
        reply = get_reply(RETURN_REPLIES, seed)
    else:
        reply = get_reply(DEFAULT_REPLIES, seed)

    await update.message.reply_text(
        f"{reply}\n\n👤 {user.full_name}  🕐 {timestamp}",
        reply_markup=MAIN_KEYBOARD,
    )


async def list_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT logged_at, user_name, action FROM work_logs ORDER BY logged_at DESC LIMIT 10"
            )
            rows = cur.fetchall()

    if not rows:
        await update.message.reply_text(
            "ยังไม่มีข้อมูลเลยค่ะ🍑 ลองกด เช็คอินสู้ตาย! ก่อนเลยนะคะ~",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    lines = ["🗒️ ประวัติล่าสุดนะคะ🍑\n"]
    for logged_at, user_name, action in reversed(rows):
        ts = logged_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{ts}] {user_name}: {action}")

    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KEYBOARD)


async def clear_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM work_logs WHERE user_id = %s",
                (update.message.from_user.id,),
            )
        conn.commit()
    await update.message.reply_text(
        "โอเคค่ะ🍑 อันยองลบข้อมูลของคุณออกหมดแล้วนะคะ เริ่มใหม่ได้เลยจ้า~",
        reply_markup=MAIN_KEYBOARD,
    )


def main():
    init_db()

    t = threading.Thread(target=run_keep_alive, daemon=True)
    t.start()

    app = Application.builder().token(TOKEN).build()

    calc_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(rf"^{BTN_CALC}$"), calc_start),
        ],
        states={
            CALC_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, calc_get_amount)],
            CALC_TYPE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, calc_get_type)],
        },
        fallbacks=[CommandHandler("cancel", calc_cancel)],
    )

    add_script_conv = ConversationHandler(
        entry_points=[CommandHandler("addscript", add_script_start)],
        states={
            ADD_SCRIPT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_script_save)],
        },
        fallbacks=[CommandHandler("cancel", add_cancel)],
    )

    add_clip_conv = ConversationHandler(
        entry_points=[CommandHandler("addclip", add_clip_start)],
        states={
            ADD_CLIP_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_clip_save)],
        },
        fallbacks=[CommandHandler("cancel", add_cancel)],
    )

    app.add_handler(calc_conv)
    app.add_handler(add_script_conv)
    app.add_handler(add_clip_conv)
    app.add_handler(CommandHandler("anyong",    anyong))
    app.add_handler(CommandHandler("start",     anyong))
    app.add_handler(CommandHandler("logs",      list_logs))
    app.add_handler(CommandHandler("clear",     clear_logs))
    app.add_handler(CommandHandler("delscript", del_script))
    app.add_handler(CommandHandler("delclip",   del_clip))
    app.add_handler(CallbackQueryHandler(script_callback, pattern=r"^script_\d+$"))
    app.add_handler(MessageHandler(filters.Regex(rf"^{BTN_SCRIPTS}$"), menu_scripts))
    app.add_handler(MessageHandler(filters.Regex(rf"^{BTN_CLIPS}$"),   menu_clips))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    time.sleep(5)
    logger.info("🚀 Anyong🍑 กำลังออนไลน์...")
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()python-telegram-bot
psycopg2-binary
