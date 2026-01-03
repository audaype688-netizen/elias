import os
import json
import random
import asyncio
from pathlib import Path

# ===== تحميل المكتبات المطلوبة =====
try:
    from dotenv import load_dotenv
    from telethon import TelegramClient
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
        JobQueue,
    )
except ImportError:
    print("="*50)
    print("خطأ: المكتبات المطلوبة غير مثبتة.")
    print("الرجاء تثبيتها باستخدام الأمر التالي:")
    print("pip install python-telegram-bot telethon python-dotenv")
    print("="*50)
    exit()

# ===== تحميل المتغيرات من ملف .env =====
load_dotenv()

# ===== متغيرات البيئة =====
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
QUOTES_DIR = os.getenv("QUOTES_DIR", "data/quotes")
CHANNELS_FILE = "data/channels.json"
SCHEDULE_FILE = "data/schedule.json"
POSTED_QUOTES_FILE = "data/posted_quotes.json" # ملف جديد لتتبع الاقتباسات المنشورة

# ===== إعداد المجلدات =====
os.makedirs(QUOTES_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

# ===== Telethon client =====
user_client = None

# ===== أدوات JSON =====
def load_json(file_path, default_value):
    if Path(file_path).exists():
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return default_value
    return default_value

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===== لوحة التحكم الرئيسية (معدّلة حسب المستخدم) =====
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = ""
    reply_markup = None

    if str(user_id) == ADMIN_ID:
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
        schedule_status = "مفعل ✅" if schedule_settings.get("enabled") else "معطل ❌"
        
        keyboard = [
            [InlineKeyboardButton("📤 نشر رسالة مخصصة", callback_data="post_custom")],
            [InlineKeyboardButton(f"🔄 النشر التلقائي: {schedule_status}", callback_data="toggle_schedule")],
            [InlineKeyboardButton("⏰ تغيير فاصل النشر", callback_data="set_interval")],
            [InlineKeyboardButton("📂 إدارة القنوات", callback_data="manage_channels")],
            [InlineKeyboardButton("➕ إضافة ملف اقتباسات", callback_data="add_quotes_file")],
            [InlineKeyboardButton("♻️ مسح سجل النشر", callback_data="reset_posted_log")], # زر جديد
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "👋 أهلاً بك يا أدمن في لوحة تحكم البوت.\n\nاختر أحد الخيارات أدناه:"
    else:
        keyboard = [
            [InlineKeyboardButton("➕ شرح كيفية إضافة قناة", callback_data="info_add_channel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = (
            "👋 أهلاً بك!\n\n"
            "هذا البوت مخصص لنشر المحتوى في قنوات تيليجرام.\n"
            "لإضافة قناتك وجعلها مؤهلة للنشر من قبل الأدمن، قم ببساطة **بإعادة توجيه (Forward)** أي رسالة من قناتك إلى هنا."
        )

    if update.callback_query:
        if update.callback_query.message.text != text or update.callback_query.message.reply_markup != reply_markup:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.callback_query.answer()
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

# ===== معالج الأزرار =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    action = query.data

    if action == "info_add_channel":
        await query.edit_message_text(
            "لإضافة قناتك، كل ما عليك فعله هو **إعادة توجيه (Forward)** أي رسالة من القناة إلى هذه المحادثة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة", callback_data="main_menu")]])
        )
        return

    if user_id != ADMIN_ID:
        await query.edit_message_text("❌ هذه الوظيفة مخصصة للأدمن فقط.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة للقائمة الرئيسية", callback_data="main_menu")]]))
        return

    if action == "main_menu":
        await main_menu(update, context)
    elif action == "post_custom":
        await query.edit_message_text("✏️ أرسل الرسالة التي تريد نشرها في القنوات:")
        context.user_data["action"] = "awaiting_custom_message"
    elif action == "add_quotes_file":
        await query.edit_message_text("📂 أرسل ملف `.txt` يحتوي على الاقتباسات.")
        context.user_data["action"] = "awaiting_quotes_file"
    elif action == "toggle_schedule":
        await toggle_schedule(update, context)
    elif action == "set_interval":
        await query.edit_message_text("⏰ أرسل الفاصل الزمني للنشر التلقائي (بالدقائق):")
        context.user_data["action"] = "awaiting_interval"
    elif action == "manage_channels":
        await manage_channels_menu(update, context)
    elif action.startswith("remove_channel_"):
        channel_id = action.split("_")[2]
        await remove_channel(update, context, channel_id)
    elif action == "reset_posted_log": # معالجة الزر الجديد
        save_json(POSTED_QUOTES_FILE, [])
        await query.answer("✅ تم مسح سجل الاقتباسات المنشورة بنجاح.")

# ===== وظائف النشر التلقائي المجدول (معدّلة بالكامل) =====
async def scheduled_post(context: ContextTypes.DEFAULT_TYPE):
    print("⏰ تنفيذ مهمة النشر التلقائي...")
    channels = load_json(CHANNELS_FILE, [])
    if not channels:
        print("⚠️ النشر التلقائي متوقف: لا توجد قنوات مضافة.")
        return

    # 1. تحميل جميع الاقتباسات المتاحة
    all_quotes = []
    quotes_files = list(Path(QUOTES_DIR).glob("*.txt"))
    if not quotes_files:
        print("⚠️ النشر التلقائي متوقف: لا توجد ملفات اقتباسات.")
        return
        
    for file in quotes_files:
        with open(file, "r", encoding="utf-8") as f:
            all_quotes.extend([line.strip() for line in f.readlines() if line.strip()])

    if not all_quotes:
        print("⚠️ النشر التلقائي متوقف: جميع ملفات الاقتباسات فارغة.")
        return

    # 2. تحميل الاقتباسات التي تم نشرها سابقاً
    posted_quotes = load_json(POSTED_QUOTES_FILE, [])

    # 3. الحصول على الاقتباسات الجديدة فقط (التي لم يتم نشرها)
    available_quotes = [q for q in all_quotes if q not in posted_quotes]

    # 4. التحقق من وجود اقتباسات جديدة
    if not available_quotes:
        print("🔔 جميع الاقتباسات قد تم نشرها. إرسال إشعار للأدمن...")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text="🔔 **تنبيه: نفاد المحتوى** 🔔\n\n"
                 "لقد تم نشر جميع الاقتباسات المتاحة.\n"
                 "الرجاء إضافة ملفات `.txt` جديدة تحتوي على اقتباسات.\n\n"
                 "سيتم الآن إعادة تعيين سجل النشر والبدء من جديد بالمحتوى الحالي."
        )
        # إعادة تعيين السجل والبدء من جديد
        save_json(POSTED_QUOTES_FILE, [])
        available_quotes = all_quotes # إعادة ملء القائمة

    # 5. اختيار اقتباس عشوائي ونشره
    message_text = random.choice(available_quotes)
    
    for channel_id in channels:
        try:
            entity = await user_client.get_input_entity(int(channel_id))
            await user_client.send_message(entity, message_text)
            print(f"✓ تم النشر التلقائي في {channel_id}")
        except Exception as e:
            print(f"✗ فشل النشر التلقائي في {channel_id}: {e}")

    # 6. تحديث قائمة الاقتباسات المنشورة
    posted_quotes.append(message_text)
    save_json(POSTED_QUOTES_FILE, posted_quotes)
    print(f"   الاقتباس '{message_text[:30]}...' تمت إضافته لسجل النشر.")


# ... (بقية الدوال تبقى كما هي: إدارة القنوات، معالج الرسائل، إلخ) ...
# ... (سأقوم بلصق الكود كاملاً للسهولة) ...

# ===== إدارة القنوات =====
async def manage_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = load_json(CHANNELS_FILE, [])
    if not channels:
        await update.callback_query.edit_message_text(
            "❌ لا توجد قنوات مضافة حالياً.\n\nلإضافة قناة، قم بإعادة توجيه رسالة منها إلى البوت.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة", callback_data="main_menu")]])
        )
        return

    keyboard = []
    for channel_id in channels:
        try:
            chat = await context.bot.get_chat(channel_id)
            keyboard.append([InlineKeyboardButton(f"🗑️ {chat.title}", callback_data=f"remove_channel_{channel_id}")])
        except Exception:
            keyboard.append([InlineKeyboardButton(f"🗑️ قناة غير معروفة ({channel_id})", callback_data=f"remove_channel_{channel_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 العودة", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("اضغط على اسم القناة لحذفها:", reply_markup=reply_markup)

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: str):
    channels = load_json(CHANNELS_FILE, [])
    if channel_id in channels:
        channels.remove(channel_id)
        save_json(CHANNELS_FILE, channels)
        await update.callback_query.answer("✅ تم حذف القناة بنجاح")
    await manage_channels_menu(update, context)

# ===== معالج الرسائل العامة =====
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = str(update.effective_user.id)

    if update.message.forward_from_chat:
        await add_channel_from_forward(update, context)
        return

    if user_id != ADMIN_ID:
        await update.message.reply_text("لإضافة قناتك، يرجى إعادة توجيه رسالة منها. للتواصل مع الأدمن، استخدم المعرف المخصص.")
        return

    user_action = context.user_data.get("action")
    
    if user_action == "awaiting_custom_message" and update.message.text:
        await receive_admin_message(update, context)
        context.user_data["action"] = None
    elif user_action == "awaiting_quotes_file" and update.message.document:
        await handle_document(update, context)
        context.user_data["action"] = None
    elif user_action == "awaiting_interval" and update.message.text:
        await set_schedule_interval(update, context)
        context.user_data["action"] = None

# ===== وظائف النشر =====
async def receive_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text
    channels = load_json(CHANNELS_FILE, [])
    if not channels:
        await update.message.reply_text("❌ لا توجد قنوات مضافة للنشر.")
        return

    results = []
    for channel_id in channels:
        try:
            entity = await user_client.get_input_entity(int(channel_id))
            await user_client.send_message(entity, msg_text)
            results.append(f"✓ {channel_id}: تم النشر")
        except Exception as e:
            results.append(f"✗ {channel_id}: فشل ({e})")

    await update.message.reply_text("📢 النشر اكتمل:\n" + "\n".join(results))
    await main_menu(update, context)

async def toggle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
    schedule_settings["enabled"] = not schedule_settings.get("enabled", False)
    save_json(SCHEDULE_FILE, schedule_settings)
    
    current_jobs = context.job_queue.get_jobs_by_name("scheduled_post")
    for job in current_jobs:
        job.schedule_removal()

    if schedule_settings["enabled"]:
        context.job_queue.run_repeating(
            scheduled_post,
            interval=schedule_settings["interval"],
            first=10,
            name="scheduled_post"
        )
        await update.callback_query.answer("✅ تم تفعيل النشر التلقائي")
    else:
        await update.callback_query.answer("❌ تم إيقاف النشر التلقائي")
        
    await main_menu(update, context)

async def set_schedule_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        interval_minutes = int(update.message.text)
        if interval_minutes < 1:
            await update.message.reply_text("❌ يجب أن يكون الفاصل الزمني دقيقة واحدة على الأقل.")
            return
        
        interval_seconds = interval_minutes * 60
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
        schedule_settings["interval"] = interval_seconds
        save_json(SCHEDULE_FILE, schedule_settings)
        
        await update.message.reply_text(f"✅ تم تحديث الفاصل الزمني إلى {interval_minutes} دقيقة.")
        
        if schedule_settings.get("enabled"):
            current_jobs = context.job_queue.get_jobs_by_name("scheduled_post")
            for job in current_jobs:
                job.schedule_removal()
            context.job_queue.run_repeating(
                scheduled_post,
                interval=interval_seconds,
                first=10,
                name="scheduled_post"
            )
    except ValueError:
        await update.message.reply_text("❌ إدخال غير صالح. الرجاء إرسال رقم فقط (عدد الدقائق).")
    
    await main_menu(update, context)

# ===== وظائف أخرى =====
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ فقط ملفات txt")
        return
    path = Path(QUOTES_DIR) / doc.file_name
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(path)
    await update.message.reply_text(f"✓ تم حفظ الملف: {doc.file_name}")
    await main_menu(update, context)

async def add_channel_from_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = msg.forward_from_chat
    if not chat or chat.type != "channel":
        await msg.reply_text("❌ الرجاء إعادة توجيه رسالة من قناة.")
        return

    try:
        await user_client.get_entity(chat.id)
    except Exception as e:
        await msg.reply_text(f"❌ لا يمكن لليوزر بوت الوصول لهذه القناة. تأكد من أن حساب المستخدم مشترك فيها.\nالخطأ: {e}")
        return

    channels = load_json(CHANNELS_FILE, [])
    if str(chat.id) in channels:
        await msg.reply_text(f"⚠️ القناة '{chat.title}' مضافة بالفعل.")
        return

    channels.append(str(chat.id))
    save_json(CHANNELS_FILE, channels)
    await msg.reply_text(f"✅ تم تفعيل القناة: {chat.title}\nسيتمكن الأدمن الآن من النشر فيها.")
    print(f"✓ قناة جديدة مضافة للنشر: {chat.title} ({chat.id}) بواسطة المستخدم {update.effective_user.full_name}")

# ===== تشغيل البوت =====
def load_scheduled_jobs(job_queue: JobQueue):
    schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
    if schedule_settings.get("enabled"):
        job_queue.run_repeating(
            scheduled_post,
            interval=schedule_settings.get("interval", 3600),
            first=10,
            name="scheduled_post"
        )
        print(f"✓ تم تحميل مهمة النشر التلقائي (كل {schedule_settings.get('interval', 3600)/60} دقيقة).")

# ===== نقطة الدخول الرئيسية =====
async def main():
    required_vars = ["API_ID", "API_HASH", "PHONE_NUMBER", "BOT_TOKEN", "ADMIN_ID"]
    if any(not os.getenv(var) for var in required_vars):
        print(f"❌ خطأ: متغيرات البيئة المطلوبة غير موجودة في ملف .env")
        return

    try:
        global API_ID, ADMIN_ID, user_client
        API_ID = int(os.getenv("API_ID"))
        ADMIN_ID = str(os.getenv("ADMIN_ID"))
    except (TypeError, ValueError) as e:
        print(f"❌ خطأ في قيم متغيرات البيئة: {e}")
        return

    user_client = TelegramClient("session_name", API_ID, API_HASH)
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", main_menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, message_handler))

    load_scheduled_jobs(app.job_queue)

    async with user_client:
        print("⏳ جاري اتصال اليوزر بوت...")
        print("✅ اليوزر بوت متصل بنجاح!")
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        print("✅ البوت جاهز للعمل!")
        await asyncio.Event().wait()
        
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 تم إيقاف البوت يدوياً.")
    except Exception as e:
        print(f"حدث خطأ غير متوقع: {e}")
