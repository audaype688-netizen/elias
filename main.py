# main.py
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ChatMemberHandler
)
import pyrogram
import config
import database as db

# إعداد التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إعداد Pyrogram Client
try:
    app_client = pyrogram.Client(
        "bot_account",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.TOKEN
    )
    pyrogram_available = True
except AttributeError:
    app_client = None
    pyrogram_available = False
    print("تنبيه: API_ID أو API_HASH غير موجودين في config.py. سيتم تجاهل Pyrogram.")

# --- دوال مساعدة ---

async def is_user_admin_in_channel(bot, user_id, channel_id):
    """التحقق ما إذا كان البوت مشرف في القناة"""
    try:
        chat_member = await bot.get_chat_member(channel_id, bot.id)
        if chat_member.status in ['administrator', 'creator']:
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

async def send_notification_to_admins(context: ContextTypes.DEFAULT_TYPE, message: str):
    """إرسال تنبيه للمطور والمشرفين"""
    session = db.Session()
    admins = session.query(db.User).filter_by(is_admin=True).all()
    for admin in admins:
        try:
            await context.bot.send_message(chat_id=admin.user_id, text=message, parse_mode='HTML')
        except:
            pass
    try:
        await context.bot.send_message(chat_id=config.DEVELOPER_ID, text=message, parse_mode='HTML')
    except:
        pass
    session.close()

# --- المفاتيح (Keyboards) ---

def get_dev_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة قناة اشتراك إجباري", callback_data="add_force_sub")],
        [InlineKeyboardButton("📂 إدارة الملفات", callback_data="manage_files")],
        [InlineKeyboardButton("👥 إدارة المشرفين", callback_data="manage_admins")],
        [InlineKeyboardButton("➕ إضافة قناة نشر", callback_data="add_channel_prompt")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
        [InlineKeyboardButton("🔊 إرسال إذاعة", callback_data="broadcast_menu")],
        [InlineKeyboardButton("⚙️ تفعيل/ايقاف النشر", callback_data="toggle_posting")],
        [InlineKeyboardButton("🚀 نشر الآن (منشور واحد)", callback_data="post_now")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📂 إدارة الملفات", callback_data="manage_files")],
        [InlineKeyboardButton("➕ إضافة قناة نشر", callback_data="add_channel_prompt")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
        [InlineKeyboardButton("🔊 إرسال إذاعة", callback_data="broadcast_menu")],
        [InlineKeyboardButton("⚙️ تفعيل/ايقاف النشر", callback_data="toggle_posting")],
        [InlineKeyboardButton("🚀 نشر الآن (منشور واحد)", callback_data="post_now")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة قناة/مجموعة", callback_data="add_channel_prompt")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard(role):
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{role}")]]
    return InlineKeyboardMarkup(keyboard)

def get_categories_keyboard():
    keyboard = [
        [InlineKeyboardButton("❤️ حب", callback_data="cat_حب")],
        [InlineKeyboardButton("🎂 عيد ميلاد", callback_data="cat_عيد ميلاد")],
        [InlineKeyboardButton("💭 اقتباسات عامة", callback_data="cat_اقتباسات عامة")],
        [InlineKeyboardButton("📜 ابيات شعرية", callback_data="cat_ابيات شعرية")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_format_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 رسالة عادية", callback_data="fmt_normal")],
        [InlineKeyboardButton("💎 Blockquote", callback_data="fmt_blockquote")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_time_keyboard():
    keyboard = [
        [InlineKeyboardButton("⏰ ساعات محددة", callback_data="time_fixed")],
        [InlineKeyboardButton("⏳ فارق زمني (دقائق)", callback_data="time_interval")],
        [InlineKeyboardButton("🚫 افتراضي (عشوائي/فوري)", callback_data="time_default")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_files_keyboard():
    keyboard = [
        [InlineKeyboardButton("❤️ حب", callback_data="upload_حب")],
        [InlineKeyboardButton("🎂 عيد ميلاد", callback_data="upload_عيد ميلاد")],
        [InlineKeyboardButton("💭 اقتباسات عامة", callback_data="upload_اقتباسات عامة")],
        [InlineKeyboardButton("📜 ابيات شعرية", callback_data="upload_ابيات شعرية")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_admin")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- المعالجات (Handlers) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    session = db.Session()
    user = session.query(db.User).filter_by(user_id=user_id).first()
    is_new_user = False
    if not user:
        user = db.User(user_id=user_id, username=username)
        session.add(user)
        session.commit()
        is_new_user = True
    else:
        if username != user.username:
            user.username = username
            session.commit()
    session.close()

    welcome_text = "أهلاً بك في بوت النشر التلقائي! 🤖"
    
    if is_new_user:
        user_tag = f"@{username}" if username else "بدون يوزر"
        msg = f"🔔 <b>تنبيه:</b> دخول شخص جديد.\n👤 الاسم: {user_tag}\n🆔 الآيدي: <code>{user_id}</code>"
        await send_notification_to_admins(context, msg)

    if user_id == config.DEVELOPER_ID:
        await update.message.reply_text(welcome_text + "\n\n🔹 <b>لوحة المطور</b> 🔹", reply_markup=get_dev_keyboard(), parse_mode='HTML')
    elif db.is_admin(user_id):
        await update.message.reply_text(welcome_text + "\n\n🔹 <b>لوحة المشرف</b> 🔹", reply_markup=get_admin_keyboard(), parse_mode='HTML')
    else:
        await update.message.reply_text(welcome_text + "\n\n🔹 <b>القائمة الرئيسية</b> 🔹", reply_markup=get_user_keyboard(), parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    # تحديد الصلاحية لتحديد زر الرجوع
    if user_id == config.DEVELOPER_ID: role = "dev"
    elif db.is_admin(user_id): role = "admin"
    else: role = "user"

    # --- قسم إدارة المشرفين (للمطور فقط) ---
    if data == "manage_admins":
        if user_id != config.DEVELOPER_ID:
            await query.edit_message_text("⛔️ هذا القسم للمطور فقط.", reply_markup=get_back_keyboard(role))
            return
        keyboard = [
            [InlineKeyboardButton("➕ إضافة مشرف", callback_data="add_admin_step1")],
            [InlineKeyboardButton("➖ حذف مشرف", callback_data="del_admin_step1")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_dev")]
        ]
        await query.edit_message_text("اختر العملية:", reply_markup=InlineKeyboardMarkup(keyboard))

    if data == "add_admin_step1":
        context.user_data['action'] = 'add_admin'
        await query.edit_message_text("أرسل الآن (آيدي) أو (معرف المستخدم) للإضافة:", reply_markup=get_back_keyboard(role))

    if data == "del_admin_step1":
        context.user_data['action'] = 'del_admin'
        await query.edit_message_text("أرسل الآن (آيدي) أو (معرف المستخدم) للحذف:", reply_markup=get_back_keyboard(role))

    # --- قسم إدارة الملفات ---
    if data == "manage_files":
        if not (user_id == config.DEVELOPER_ID or db.is_admin(user_id)):
            return 
        await query.edit_message_text("اختر القسم لرفع ملفات الاقتباسات (txt):", reply_markup=get_files_keyboard())

    if data.startswith("upload_"):
        category = data.split("_")[1]
        context.user_data['upload_category'] = category
        msg = f"تم اختيار قسم: <b>{category}</b>\n\nالآن قم بإرسال ملف <code>.txt</code> يحتوي على الاقتباسات.\n(سيتم إضافتها للقائمة الحالية ولن يتم حذف القديم)."
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))

    # --- إضافة قناة ---
    if data == "add_channel_prompt":
        context.user_data['step'] = 'waiting_channel'
        await query.edit_message_text("✏️ قم بإرسال معرف القناة (مثلاً @ChannelName) أو قم بتحويل رسالة (Forward) من القناة هنا:", reply_markup=get_back_keyboard(role))

    # --- اختيار القسم عند الإضافة ---
    if data.startswith("cat_"):
        category = data.split("_")[1]
        context.user_data['selected_category'] = category
        msg = f"تم اختيار القسم: <b>{category}</b>.\n\nاختر شكل الرسالة:"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_format_keyboard())

    # --- اختيار التنسيق ---
    if data.startswith("fmt_"):
        fmt = data.split("_")[1]
        category = context.user_data.get('selected_category')
        context.user_data['selected_format'] = fmt
        await query.edit_message_text("اختر طريقة النشر:", reply_markup=get_time_keyboard())

    if data.startswith("time_"):
        time_type = data.split("_")[1]
        context.user_data['time_type'] = time_type
        
        msg = ""
        if time_type == "fixed":
            context.user_data['action'] = 'set_fixed_time'
            msg = "أرسل الساعات المطلوبة (مثلاً: 10, 14, 20) مفصولة بفاصلة:"
        elif time_type == "interval":
            context.user_data['action'] = 'set_interval'
            msg = "أرسل الفارق الزمني بالدقائق (مثلاً: 60):"
        else:
            # افتراضي
            await finalize_channel_addition(update, context, query, role)
            return
        
        await query.edit_message_text(msg, reply_markup=get_back_keyboard(role))

    # --- أزرار عامة ---
    if data == "show_stats":
        stats = db.get_stats()
        await query.edit_message_text(stats, parse_mode='HTML', reply_markup=get_back_keyboard(role))

    # أزرار الرجوع الموحدة
    if data == "back_home":
        kb = get_dev_keyboard() if role == "dev" else (get_admin_keyboard() if role == "admin" else get_user_keyboard())
        title = "لوحة المطور:" if role == "dev" else ("لوحة المشرف:" if role == "admin" else "القائمة الرئيسية:")
        await query.edit_message_text(title, reply_markup=kb)

    if data == "back_dev":
        await query.edit_message_text("لوحة المطور:", reply_markup=get_dev_keyboard())
    
    if data == "back_admin":
        await query.edit_message_text("لوحة المشرف:", reply_markup=get_admin_keyboard())

    if data == "back_user":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=get_user_keyboard())

    # --- النشر التلقائي وإيقافه ---
    if data == "toggle_posting":
        session = db.Session()
        setting = session.query(db.BotSettings).filter_by(key='posting_status').first()
        status = setting.value if setting else 'off'
        new_status = 'on' if status == 'off' else 'off'
        
        if setting:
            setting.value = new_status
        else:
            session.add(db.BotSettings(key='posting_status', value=new_status))
        session.commit()
        session.close()
        
        state_text = "🟢 مفعل" if new_status == 'on' else "🔴 متوقف"
        msg = f"تم تغيير حالة النشر إلى: <b>{state_text}</b>"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))

    if data == "post_now":
        await query.edit_message_text("جاري بدء النشر الفوري...")
        await post_job(context, force_one=True)
        msg = "تم النشر الفوري بنجاح ✅"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))

    if data == "broadcast_menu":
        if not db.is_admin(user_id): return
        context.user_data['action'] = 'waiting_broadcast'
        await query.edit_message_text("✏️ أرسل الرسالة التي تريد إذاعتها للخاص والقنوات:", reply_markup=get_back_keyboard(role))


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    document = update.message.document
    
    # تعديل: التحقق من وجود forward_from_chat قبل تعيينه لتفادي الخطأ
    forward_from = None
    if update.message.forward_from_chat:
        forward_from = update.message.forward_from_chat
    
    # تحديد الرول
    if user_id == config.DEVELOPER_ID: role = "dev"
    elif db.is_admin(user_id): role = "admin"
    else: role = "user"

    # --- إضافة مشرف ---
    if context.user_data.get('action') == 'add_admin':
        target = text.strip().replace("@", "")
        session = db.Session()
        user = session.query(db.User).filter((db.User.username == target) | (db.User.user_id == str(target))).first()
        if user:
            user.is_admin = True
            session.commit()
            msg = f"✅ تم رفع @{user.username} مشرفاً بنجاح."
        else:
            msg = "❌ المستخدم غير موجود في قاعدة بيانات البوت. تأكد أن الشخص قد بدأ البوت (/start)."
        session.close()
        context.user_data['action'] = None
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
        return

    if context.user_data.get('action') == 'del_admin':
        target = text.strip().replace("@", "")
        session = db.Session()
        user = session.query(db.User).filter((db.User.username == target) | (db.User.user_id == str(target))).first()
        if user and user.user_id != config.DEVELOPER_ID:
            user.is_admin = False
            session.commit()
            msg = f"✅ تم إزالة صلاحية المشرف من @{user.username}."
        else:
            msg = "❌ حدث خطأ أو تحاول حذف المطور."
        session.close()
        context.user_data['action'] = None
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
        return

    # --- رفع الملفات ---
    if document and context.user_data.get('upload_category'):
        category = context.user_data['upload_category']
        if document.mime_type == "text/plain":
            file = await document.get_file()
            content_bytes = await file.download_as_bytearray()
            content_text = content_bytes.decode('utf-8').splitlines()
            content_list = [line for line in content_text if line.strip()]
            
            count = db.add_file_content(category, content_list)
            msg = f"✅ تمت إضافة <b>{count}</b> اقتباس لقسم <b>{category}</b> بنجاح.\n(تمت الإضافة للقائمة الحالية)."
            context.user_data['upload_category'] = None
        else:
            msg = "❌ يرجى رفع ملف بصيغة .txt فقط."
        
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
        return

    # --- إضافة قناة (استقبال التحويل أو المعرف) ---
    if context.user_data.get('step') == 'waiting_channel':
        channel_id = None
        title = ""
        
        # التحقق من وجود تحويلة
        if forward_from:
            channel_id = forward_from.id
            title = forward_from.title
        elif text and (text.startswith("@") or text.startswith("-100")):
            try:
                chat = await context.bot.get_chat(text)
                channel_id = chat.id
                title = chat.title
            except:
                msg = "❌ تعذر الوصول للقناة. تأكد من المعرف وأن البوت مشرف."
                await update.message.reply_text(msg, reply_markup=get_back_keyboard(role))
                return
        else:
            # إذا لم يرسل تحويلة ولا معرف صحيح، لا نفعل شيئاً (ننتظر رسالة صحيحة)
            return

        is_bot_admin = await is_user_admin_in_channel(context.bot, user_id, channel_id)
        
        if not is_bot_admin:
            msg = f"⛔️ <b>تنبيه:</b> أنا لست مشرفاً في القناة [<b>{title}</b>].\n\nيرجى رفعي مشرفاً ثم إعادة المحاولة."
            await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
            return

        context.user_data['pending_channel'] = {'id': channel_id, 'title': title}
        context.user_data['step'] = None
        msg = f"✅ تم التحقق من القناة: <b>{title}</b>\n\nالآن اختر نوع الاقتباسات لهذه القناة:"
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_categories_keyboard())
        return

    # --- إعدادات الوقت ---
    if context.user_data.get('action') == 'set_fixed_time':
        context.user_data['time_settings'] = {'type': 'fixed', 'value': text}
        await finalize_channel_addition(update, context, None, role)
        return

    if context.user_data.get('action') == 'set_interval':
        context.user_data['time_settings'] = {'type': 'interval', 'value': int(text)}
        await finalize_channel_addition(update, context, None, role)
        return

    # --- الإذاعة ---
    if context.user_data.get('action') == 'waiting_broadcast':
        msg_to_send = update.message.text or update.message.caption
        if not msg_to_send: return
        
        success_count = 0
        session = db.Session()
        users = session.query(db.User).all()
        channels = session.query(db.Channel).all()
        
        for u in users:
            try:
                await context.bot.send_message(chat_id=u.user_id, text=msg_to_send)
                success_count += 1
                await asyncio.sleep(0.1)
            except:
                pass
                
        for c in channels:
            try:
                await context.bot.send_message(chat_id=c.channel_id, text=msg_to_send)
                success_count += 1
            except:
                pass
        
        session.close()
        msg = f"✅ تم إرسال الإذاعة بنجاح إلى <b>{success_count}</b> جهة."
        context.user_data['action'] = None
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
        return

    # --- تفعيل المجموعات ---
    if text == "تفعيل":
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        
        if chat_type in ['group', 'supergroup']:
            is_bot_admin = await is_user_admin_in_channel(context.bot, user_id, chat_id)
            if not is_bot_admin:
                await update.message.reply_text("يجب أن أكون مشرفاً في المجموعة للتفعيل.")
                return
            
            db.add_channel(chat_id, update.effective_chat.title, user_id, "اقتباسات عامة", "normal")
            await update.message.reply_text("✅ تم تفعيل البوت في المجموعة بنجاح!")

async def finalize_channel_addition(update, context, query, role):
    """دالة مساعدة لإنهاء إضافة القناة مع زر رجوع"""
    pending = context.user_data.get('pending_channel')
    if not pending: return
    
    cat = context.user_data.get('selected_category')
    fmt = context.user_data.get('selected_format', 'normal')
    
    db.add_channel(pending['id'], pending['title'], update.effective_user.id, cat, fmt)
    
    context.user_data['pending_channel'] = None
    context.user_data['selected_category'] = None
    
    msg = f"✅ تمت إضافة القناة بنجاح!\n📂 القسم: <b>{cat}</b>\n📝 الشكل: {fmt}"
    
    # تحديد نوع الإرسال (Edit أو Reply)
    if query:
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
    else:
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))

# --- وظائف النشر (Scheduler Logic) ---

async def post_job(context: ContextTypes.DEFAULT_TYPE, force_one=False):
    """الوظيفة المسؤولة عن النشر التلقائي"""
    session = db.Session()
    setting = session.query(db.BotSettings).filter_by(key='posting_status').first()
    if not force_one and (not setting or setting.value == 'off'):
        session.close()
        return

    channels = session.query(db.Channel).filter_by(is_active=True).all()
    session.close()

    if not channels:
        return

    for channel in channels:
        try:
            text = db.get_next_content(channel.category)
            if not text:
                continue

            if channel.msg_format == 'blockquote':
                # تنسيق HTML للـ Blockquote
                text = f"<blockquote>{text}</blockquote>"
                parse_mode = 'HTML'
            else:
                parse_mode = None

            await context.bot.send_message(
                chat_id=channel.channel_id,
                text=text,
                parse_mode=parse_mode
            )
            
            if force_one:
                return
            await asyncio.sleep(1) 

        except Exception as e:
            logger.error(f"Failed to post to {channel.title}: {e}")
            if "Chat not found" in str(e) or "Forbidden" in str(e):
                await send_notification_to_admins(context, f"⚠️ تم حذف البوت من القناة: {channel.title}.\nسأقوم بحذفها من القاعدة.")
                db.remove_channel_db(channel.channel_id)

# --- معالجة مغادرة البوت ---
async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if result.old_chat_member.status in ['administrator', 'member'] and \
       result.new_chat_member.status in ['left', 'kicked']:
        
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title
        
        asyncio.create_task(send_notification_to_admins(context, f"⚠️ تم حذف البوت من <b>{chat_title}</b>"))
        db.remove_channel_db(chat_id)

# --- تشغيل البوت ---

def main():
    db.Base.metadata.create_all(db.engine)
    
    application = Application.builder().token(config.TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT | filters.FORWARDED & filters.ChatType.PRIVATE, message_handler))
    application.add_handler(MessageHandler(filters.Document.MimeType("text/plain") & filters.ChatType.PRIVATE, message_handler))
    application.add_handler(MessageHandler(filters.Regex("^تفعيل$") & filters.ChatType.GROUPS, message_handler))
    application.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.CHAT_MEMBER))

    # تشغيل النشر التلقائي كل ساعة
    job_queue = application.job_queue
    job_queue.run_repeating(post_job, interval=3600, first=10)

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    # تشغيل Pyrogram إذا كانت البيانات متوفرة، مع منع الأخطاء من إيقاف البوت
    if hasattr(config, 'API_ID') and hasattr(config, 'API_HASH'):
        if config.API_ID and config.API_HASH:
            try:
                app_client.start()
            except Exception as e:
                print(f"Warning: Pyrogram failed to start: {e}")
                print("Continuing with python-telegram-bot only...")
    
    main()
