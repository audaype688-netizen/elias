import os
import json
import random
import asyncio
import logging
import shutil
import time
import tempfile
import zipfile
import sys
from pathlib import Path
from typing import Any, List, Dict
from functools import wraps
from html import escape
from datetime import time as dt_time

# ===== تحميل المكتبات =====
try:
    from dotenv import load_dotenv
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
except ImportError as e:
    print("="*50)
    missing_lib = str(e).split("'")[1] if "'" in str(e) else e
    print(f"❌ خطأ: المكتبات المطلوبة غير مثبتة.")
    print(f"المكتبة الناقصة: {missing_lib}")
    print("تثبيت: pip install python-telegram-bot==20.7 python-dotenv")
    print("="*50)
    exit(1)

# إعداد التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== تحميل المتغيرات =====
load_dotenv(override=True)

required_vars = ["BOT_TOKEN", "ADMIN_ID"]
for var in required_vars:
    value = os.getenv(var)
    if not value:
        logger.critical(f"❌ متغير البيئة المفقود: {var}")
        exit(1)

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except ValueError:
    logger.critical("❌ ADMIN_ID يجب أن يكون رقمًا")
    exit(1)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_DIR = Path("data").resolve()
QUOTES_DIR = BASE_DIR / "quotes"
IMAGES_DIR = BASE_DIR / "images"
CHANNELS_FILE = BASE_DIR / "channels.json"
SCHEDULE_FILE = BASE_DIR / "schedule.json"
POSTED_QUOTES_FILE = BASE_DIR / "posted_quotes.json"
LAST_MSG_FILE = BASE_DIR / "last_messages.json"

MAX_POSTED_QUOTES = 5000 
IMAGE_POST_INTERVAL = 5 

# إنشاء المجلدات
QUOTES_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ===== أدوات JSON =====
def load_json(file_path: Path, default_value: Any = None) -> Any:
    if default_value is None:
        default_value = {}
    if not file_path.exists():
        return default_value
    
    try:
        with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
            content = f.read().strip()
            if not content:
                return default_value
            return json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"❌ خطأ في قراءة {file_path.name}: {e}")
        backup_path = file_path.with_suffix(f'.json.bak.{int(time.time())}')
        shutil.copy2(file_path, backup_path)
        return default_value

def save_json(file_path: Path, data: Any) -> bool:
    try:
        # التأكد من أن البيانات ليست فارغة
        if not data:
            logger.warning(f"⚠️ محاولة حفظ بيانات فارغة في {file_path.name} تم إلغاؤها.")
            return False

        temp_path = file_path.with_suffix('.tmp')
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        if file_path.exists():
            file_path.unlink()
        temp_path.rename(file_path)
        
        logger.debug(f"✅ تم حفظ {file_path.name} بنجاح")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ {file_path.name}: {e}")
        temp_path = file_path.with_suffix('.tmp')
        if temp_path.exists():
            temp_path.unlink()
        return False

# ===== إدارة القنوات والمجموعات =====
def load_channels_data() -> List[Dict]:
    data = load_json(CHANNELS_FILE, [])
    
    # حماية إضافية من فقدان البيانات
    if not data:
        logger.warning("⚠️ بيانات القنوات فارغة.")
    
    if isinstance(data[0], str) if data else False:
        logger.info("🔄 تحويل بيانات القنوات من البنية القديمة...")
        new_data = [{"id": cid, "type": "channel", "title": "غير معروف", "fails": 0} for cid in data]
        save_json(CHANNELS_FILE, new_data)
        return new_data
    
    for item in data:
        if "fails" not in item:
            item["fails"] = 0
    return data

def save_channels_data(data: List[Dict]) -> bool:
    return save_json(CHANNELS_FILE, data)

def add_chat_to_data(chat_info: Dict) -> bool:
    try:
        data = load_channels_data()
        chat_id_str = str(chat_info["id"])
        for item in data:
            if item["id"] == chat_id_str:
                item["fails"] = 0
                save_channels_data(data)
                return False 
        chat_info["fails"] = 0
        data.append(chat_info)
        return save_channels_data(data)
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة الدردشة: {e}")
        return False

def remove_chat_from_data(chat_id: str) -> bool:
    try:
        data = load_channels_data()
        initial_length = len(data)
        data = [item for item in data if item["id"] != chat_id]
        if len(data) < initial_length:
            return save_channels_data(data)
        return False
    except Exception as e:
        logger.error(f"❌ خطأ في حذف الدردشة: {e}")
        return False

def update_fail_count(chat_id: str, failed: bool):
    try:
        data = load_channels_data()
        for item in data:
            if item["id"] == chat_id:
                if failed:
                    item["fails"] = item.get("fails", 0) + 1
                    logger.warning(f"⚠️ فشل في {chat_id} (العداد: {item['fails']})")
                else:
                    item["fails"] = 0
                break
        save_channels_data(data)
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث عداد الفشل: {e}")

# ===== كاش الاقتباسات =====
class QuotesCache:
    def __init__(self, quotes_dir: Path):
        self.quotes_dir = quotes_dir
        self._cache: list[str] = []
        self._cache_time: float = 0
        self._file_times: dict[str, float] = {}
    
    async def get_all_quotes(self) -> list[str]:
        now = time.time()
        if now - self._cache_time > 300:
            await self._reload_cache()
            self._cache_time = now
        return self._cache.copy()
    
    async def _reload_cache(self):
        current_files = {f.name: f.stat().st_mtime for f in self.quotes_dir.glob("*.txt") if f.is_file()}
        if self._file_times == current_files and self._cache:
            return
        
        logger.info("🔄 تحديث كاش الاقتباسات...")
        self._cache = []
        
        for filename, mtime in current_files.items():
            file = self.quotes_dir / filename
            try:
                loop = asyncio.get_event_loop()
                lines = await loop.run_in_executor(None, self._read_file, file)
                valid_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) <= 4096]
                self._cache.extend(valid_lines)
                self._file_times[filename] = mtime
            except Exception as e:
                logger.error(f"❌ خطأ في قراءة {filename}: {e}")
        
        logger.info(f"✅ {len(self._cache):,} أذكار جاهزة")
    
    @staticmethod
    def _read_file(file: Path) -> list[str]:
        try:
            with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                return f.readlines()
        except:
            return []

quotes_cache = QuotesCache(QUOTES_DIR)

# ===== ديكور الأدمن فقط =====
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID:
            if update.callback_query:
                await update.callback_query.answer("❌ للأدمن فقط!", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ===== معالج الأخطاء =====
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception:", exc_info=context.error)
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ خطأ: {str(context.error)[:200]}", disable_notification=True)
    except:
        pass

# ===== البدء =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id == ADMIN_ID:
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600})
        is_enabled = schedule_settings.get("enabled", False)
        status_emoji = "🟢" if is_enabled else "🔴"
        status_text = "مفعل" if is_enabled else "معطل"

        keyboard = [
            [
                InlineKeyboardButton("📊 إحصائيات", callback_data="show_stats"),
                InlineKeyboardButton(f"{status_emoji} التلقائي", callback_data="toggle_schedule")
            ],
            [
                InlineKeyboardButton("📤 نشر نص", callback_data="post_custom_text"),
                InlineKeyboardButton("🖼️ نشر صورة", callback_data="post_custom_photo")
            ],
            [
                InlineKeyboardButton("⏰ تعديل الفاصل", callback_data="set_interval"),
                InlineKeyboardButton("✏️ تعديل آخر رسالة", callback_data="edit_last")
            ],
            [
                InlineKeyboardButton("📂 القنوات", callback_data="manage_channels"),
                InlineKeyboardButton("➕ أضف أذكار/صور", callback_data="add_content")
            ],
            [
                InlineKeyboardButton("🗑️ مسح السجل", callback_data="reset_posted_log"),
                InlineKeyboardButton("💾 استعادة نسخة", callback_data="restore_backup")
            ]
        ]
        text = "<blockquote>لوحة التحكم 🎛️</blockquote>"

    else:
        keyboard = [
            [InlineKeyboardButton(
                "➕ أضفني إلى قناة أو مجموعة",
                url=f"https://t.me/{context.bot.username}?startgroup=true"
            )]
        ]
        text = """
🌙 أهلا بك في بوت نشر الأذكار التلقائي 🌙

قم بإضافة البوت إلى قناتك أو مجموعتك لتفعيل خدمة الأذكار والآيات.
ارسل كلمة <b>تفعيل</b> للتفعيل في المجموعة.

<blockquote>البوت يرسل أذكار وآيات قرآنية بشكل دوري</blockquote>

تواصل مع المدير @s_x_n
"""

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")

# ===== معالج الملفات =====
@admin_only
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_action = context.user_data.get("action")
    doc = update.message.document
    if not doc: return
    file_name = doc.file_name.lower()

    # 1. رفع ملف نصي
    if user_action == "awaiting_quotes_file":
        if doc.mime_type != "text/plain":
            await update.message.reply_text("❌ يرجى إرسال ملف نصي .txt فقط!")
            return

        context.user_data.clear()
        safe_filename = Path(doc.file_name).name
        path = QUOTES_DIR / safe_filename
        
        try:
            file = await context.bot.get_file(doc.file_id)
            await file.download_to_drive(path)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = sum(1 for line in f if line.strip())
            
            if lines == 0:
                path.unlink()
                await update.message.reply_text("⚠️ الملف فارغ!")
                return
            
            quotes_cache._cache_time = 0
            await update.message.reply_text(f"✅ تم حفظ الأذكار: {safe_filename}\n📝 {lines:,} سطر")
            await start(update, context)
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل الملف: {e}")
            if path.exists(): path.unlink()

    # 2. رفع ملف صور مضغوط
    elif user_action == "awaiting_images_zip":
        if not file_name.endswith('.zip'):
            await update.message.reply_text("❌ يرجى إرسال ملف بصيغة .zip فقط!")
            return

        context.user_data.clear()
        await update.message.reply_text("⏳ جاري فك ضغط وحفظ الصور...")
        
        temp_zip_path = BASE_DIR / f"temp_{doc.file_name}"
        try:
            new_file = await context.bot.get_file(doc.file_id)
            await new_file.download_to_drive(temp_zip_path)
            
            count = 0
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.endswith('/'): continue
                    filename = Path(member).name
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        source = zip_ref.open(member)
                        target = open(IMAGES_DIR / filename, "wb")
                        with source, target:
                            shutil.copyfileobj(source, target)
                        count += 1
            
            temp_zip_path.unlink()
            await update.message.reply_text(f"✅ تم حفظ {count} صورة بنجاح!")
            await start(update, context)

        except Exception as e:
            logger.error(f"❌ خطأ في معالجة الصور: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء معالجة الملف.")
            if temp_zip_path.exists(): temp_zip_path.unlink()

    # 3. استعادة النسخة الاحتياطية
    elif user_action == "awaiting_restore_file":
        if not file_name.endswith('.zip'):
            await update.message.reply_text("❌ يرجى إرسال ملف بصيغة .zip فقط!")
            return

        context.user_data.clear()
        await update.message.reply_text("⏳ جاري استعادة البيانات... سيتم إيقاف البوت.")
        
        temp_zip_path = BASE_DIR / f"restore_{doc.file_name}"
        try:
            new_file = await context.bot.get_file(doc.file_id)
            await new_file.download_to_drive(temp_zip_path)
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)
                
                restored_files = []
                for f in temp_path.glob("*"):
                    if f.is_file() and f.suffix == ".json":
                        target_file = BASE_DIR / f.name
                        shutil.copy2(f, target_file)
                        restored_files.append(f.name)
                
                if not restored_files:
                    await update.message.reply_text("❌ الملف لا يحتوي على بيانات صالحة (JSON).")
                    if temp_zip_path.exists(): temp_zip_path.unlink()
                    return
            
            temp_zip_path.unlink()
            
            logger.info("✅ تم استعادة البيانات بنجاح. جاري إيقاف التشغيل.")
            # في الاستضافة لا نعيد التشغيل، بل نوقف ونترك الـ Manager يدير الأمر
            sys.exit(0)

        except Exception as e:
            logger.error(f"❌ خطأ في الاستعادة: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء استعادة البيانات.")
            if temp_zip_path.exists(): temp_zip_path.unlink()

# ===== معالج الرسائل العام =====
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user_id = update.effective_user.id
    text = update.message.text
    user_action = context.user_data.get("action")

    if text and text.strip().replace("/", "") == "تفعيل" and update.message.chat.type in ['channel', 'group', 'supergroup']:
        await activate_bot_in_channel_or_group(update, context)
        return

    if update.message.forward_from_chat:
        if update.message.forward_from_chat.type in ['channel', 'group', 'supergroup']:
            await add_channel_or_group_from_forward(update, context)
        return

    if user_id != ADMIN_ID:
        if text: await update.message.reply_text("لإضافة قناتك، قم بتوجيه رسالة منها.")
        return

    if user_action == "awaiting_custom_text":
        if text: await receive_admin_text(update, context)
        context.user_data.clear()
    elif user_action == "awaiting_custom_photo_caption":
        if text: await receive_admin_photo(update, context)
        context.user_data.clear()
    elif user_action == "awaiting_edit_text":
        if text: await process_edit_message(update, context)
        context.user_data.clear()
    elif user_action == "awaiting_interval":
        if text and text.isdigit():
            await set_schedule_interval(update, context)
            context.user_data.clear()
        else:
            await update.message.reply_text("❌ الرجاء إرسال رقم صحيح.")
    elif user_action:
        context.user_data.clear()
        await start(update, context)

# ===== تفعيل البوت =====
async def activate_bot_in_channel_or_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['channel', 'group', 'supergroup']:
        await update.message.reply_text("❌ يمكن التفعيل فقط في القنوات أو المجموعات!")
        return
    try:
        test_msg = await context.bot.send_message(chat_id=chat.id, text="🔍 ...", disable_notification=True)
        try: await context.bot.delete_message(chat_id=chat.id, message_id=test_msg.message_id)
        except: pass
    except Exception as e:
        await update.message.reply_text("❌ البوت لا يملك الصلاحيات الكافية!")
        return

    chat_info = {"id": str(chat.id), "type": chat.type, "title": chat.title or "غير معروف"}
    if add_chat_to_data(chat_info):
        await update.message.reply_text("✅ تم التفعيل بنجاح!")
    else:
        await update.message.reply_text("⚠️ القناة/المجموعة مضافة بالفعل.")

# ===== إضافة من توجيه =====
async def add_channel_or_group_from_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    forward_chat = msg.forward_from_chat

    if not forward_chat or forward_chat.type not in ['channel', 'group', 'supergroup']:
        await msg.reply_text("❌ الرجاء إعادة توجيه رسالة من قناة أو مجموعة فقط.")
        return

    try:
        test_msg = await context.bot.send_message(chat_id=forward_chat.id, text="🔍 ...", disable_notification=True)
        try: await context.bot.delete_message(chat_id=forward_chat.id, message_id=test_msg.message_id)
        except: pass
    except Exception as e:
        await msg.reply_text("❌ البوت لا يملك الصلاحيات الكافية!")
        return

    chat_info = {"id": str(forward_chat.id), "type": forward_chat.type, "title": forward_chat.title or "غير معروف"}
    if add_chat_to_data(chat_info):
        await msg.reply_text(f"✅ تمت إضافة {forward_chat.title}")
    else:
        await msg.reply_text("⚠️ مضافة بالفعل.")

# ===== معالج الأزرار =====
@admin_only
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    
    try:
        if action == "main_menu":
            await start(update, context)
        elif action == "show_stats":
            await show_stats(update, context)
        elif action == "post_custom_text":
            await query.edit_message_text("✏️ أرسل النص للنشر:")
            context.user_data["action"] = "awaiting_custom_text"
        elif action == "post_custom_photo":
            await query.edit_message_text("🖼️ سيتم نشر صورة عشوائية.\n✏️ أرسل النص (التعليق) للصورة:")
            context.user_data["action"] = "awaiting_custom_photo_caption"
        elif action == "edit_last":
            await query.edit_message_text("✏️ أرسل النص الجديد للتعديل:")
            context.user_data["action"] = "awaiting_edit_text"
        elif action == "add_content":
            keyboard = [
                [InlineKeyboardButton("📝 رفع ملف أذكار (TXT)", callback_data="add_quotes_file")],
                [InlineKeyboardButton("📦 رفع صور (ZIP)", callback_data="upload_images")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
            ]
            await query.edit_message_text("اختر نوع المحتوى:", reply_markup=InlineKeyboardMarkup(keyboard))
        elif action == "add_quotes_file":
            await query.edit_message_text("📂 أرسل ملف .txt:")
            context.user_data["action"] = "awaiting_quotes_file"
        elif action == "upload_images":
            await query.edit_message_text("📦 أرسل ملف .zip يحتوي على الصور:")
            context.user_data["action"] = "awaiting_images_zip"
        elif action == "manage_channels":
            await manage_channels_menu(update, context)
        elif action.startswith("remove_chat_"):
            chat_id = action.split("_", 2)[2]
            await remove_chat(update, context, chat_id)
        elif action == "toggle_schedule":
            await toggle_schedule(update, context)
        elif action == "set_interval":
            await query.edit_message_text("⏰ أرسل الفاصل بالدقائق (1-1440):")
            context.user_data["action"] = "awaiting_interval"
        elif action == "reset_posted_log":
            save_json(POSTED_QUOTES_FILE, [])
            await query.answer("✅ تم مسح السجل", show_alert=True)
        elif action == "restore_backup":
            await query.edit_message_text("📂 أرسل ملف النسخة الاحتياطية (.zip) لاستعادة البيانات:")
            context.user_data["action"] = "awaiting_restore_file"
    except Exception as e:
        logger.error(f"❌ خطأ في معالج الأزرار: {e}")

# ===== نشر نص مخصص =====
async def receive_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text
    if not msg_text or len(msg_text) > 4096:
        await update.message.reply_text("❌ نص غير صالح!")
        return

    channels_data = load_channels_data()
    if not channels_data:
        await update.message.reply_text("❌ لا توجد قنوات.")
        return

    results = []
    last_msgs = load_json(LAST_MSG_FILE, {})
    updated_last_msgs = {}

    for item in channels_data:
        try:
            sent_msg = await context.bot.send_message(
                chat_id=int(item["id"]),
                text=f"<b>{msg_text}</b>",
                parse_mode="HTML"
            )
            results.append(f"✅ {item['id']}")
            updated_last_msgs[str(item["id"])] = sent_msg.message_id
        except Exception as e:
            results.append(f"❌ {item['id']}: {str(e)[:30]}")

    save_json(LAST_MSG_FILE, updated_last_msgs)
    await update.message.reply_text("📢 النشر اكتمل:\n" + "\n".join(results[:20]))
    await start(update, context)

# ===== نشر صورة مخصصة =====
async def receive_admin_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption_text = update.message.text or ""
    if len(caption_text) > 1024:
        await update.message.reply_text("❌ النص طويل جداً!")
        return

    channels_data = load_channels_data()
    if not channels_data:
        await update.message.reply_text("❌ لا توجد قنوات.")
        return

    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.png")) + list(IMAGES_DIR.glob("*.jpeg")) + list(IMAGES_DIR.glob("*.webp"))
    if not images:
        await update.message.reply_text("⚠️ لا توجد صور في المجلد. قم برفع ملف ZIP أولاً.")
        return

    random_image = random.choice(images)
    results = []
    last_msgs = load_json(LAST_MSG_FILE, {})
    updated_last_msgs = {}

    for item in channels_data:
        try:
            with open(random_image, 'rb') as photo_file:
                sent_msg = await context.bot.send_photo(
                    chat_id=int(item["id"]),
                    photo=photo_file,
                    caption=f"<b>{caption_text}</b>",
                    parse_mode="HTML"
                )
            results.append(f"✅ {item['id']}")
            updated_last_msgs[str(item["id"])] = sent_msg.message_id
        except Exception as e:
            results.append(f"❌ {item['id']}: {str(e)[:30]}")

    save_json(LAST_MSG_FILE, updated_last_msgs)
    await update.message.reply_text(f"🖼️ نشر صورة ({random_image.name})\n📢 النشر اكتمل:\n" + "\n".join(results[:20]))
    await start(update, context)

# ===== تعديل آخر رسالة =====
async def process_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text
    if not new_text or len(new_text) > 4096:
        await update.message.reply_text("❌ نص غير صالح!")
        return

    channels_data = load_channels_data()
    last_msgs = load_json(LAST_MSG_FILE, {})
    
    if not last_msgs:
        await update.message.reply_text("⚠️ لا يوجد سجل لرسائل سابقة.")
        await start(update, context)
        return

    results = []
    for item in channels_data:
        chat_id_str = str(item["id"])
        if chat_id_str in last_msgs:
            try:
                await context.bot.edit_message_text(
                    chat_id=int(chat_id_str),
                    message_id=last_msgs[chat_id_str],
                    text=f"<b>{new_text}</b>",
                    parse_mode="HTML"
                )
                results.append(f"✅ تعديل {item['id']}")
            except Exception as e:
                if "not found" in str(e).lower() or "can't be edited" in str(e).lower():
                    del last_msgs[chat_id_str]
                    save_json(LAST_MSG_FILE, last_msgs)
                results.append(f"❌ {item['id']}: {str(e)[:30]}")
        else:
            results.append(f"⏭️ {item['id']}: لا يوجد سجل")

    await update.message.reply_text("📝 نتائج التعديل:\n" + "\n".join(results[:20]))
    await start(update, context)

# ===== الإحصائيات =====
@admin_only
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels_data = load_channels_data()
    all_quotes = await quotes_cache.get_all_quotes()
    schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False})
    failed_channels = [c for c in channels_data if c.get("fails", 0) > 0]
    
    images_count = len(list(IMAGES_DIR.glob("*.*")))
    
    text = f"""
📊 <b>إحصائيات البوت:</b>

📢 القنوات: {sum(1 for x in channels_data if x['type'] == 'channel')}
👥 المجموعات: {sum(1 for x in channels_data if x['type'] in ['group', 'supergroup'])}
📝 الأذكار: {len(all_quotes):,}
🖼️ الصور: {images_count}
⏰ التلقائي: {'مفعل' if schedule_settings.get('enabled') else 'معطل'}
⚠️ قنوات بها مشاكل: {len(failed_channels)}
"""
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]
    await update.callback_query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== النسخ الاحتياطي =====
async def manual_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("جاري إنشاء النسخة...", show_alert=True)
    try:
        temp_zip = Path(f"temp_backup_{int(time.time())}.zip")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            files_to_backup = [CHANNELS_FILE, SCHEDULE_FILE, POSTED_QUOTES_FILE, LAST_MSG_FILE]
            for f in files_to_backup:
                if f.exists(): shutil.copy2(f, temp_path / f.name)
            
            shutil.make_archive(str(temp_zip.with_suffix('')), 'zip', temp_path)
        
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=open(temp_zip, 'rb'),
            caption=f"💾 نسخة احتياطية: {time.strftime('%Y-%m-%d %H:%M')}"
        )
        temp_zip.unlink()
        await start(update, context)
    except Exception as e:
        logger.error(f"❌ فشل النسخ الاحتياطي: {e}")
        await update.callback_query.answer("❌ فشلت العملية!", show_alert=True)

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("💾 بدء النسخ الاحتياطي...")
    try:
        temp_zip = Path(f"daily_backup_{int(time.time())}.zip")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            files_to_backup = [CHANNELS_FILE, SCHEDULE_FILE, POSTED_QUOTES_FILE, LAST_MSG_FILE]
            for f in files_to_backup:
                if f.exists():
                    shutil.copy2(f, temp_path / f.name)
            
            shutil.make_archive(str(temp_zip.with_suffix('')), 'zip', temp_path)
        
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=open(temp_zip, 'rb'),
            caption=f"📅 نسخة احتياطية دورية: {time.strftime('%Y-%m-%d %H:%M')}"
        )
        temp_zip.unlink()
        logger.info("✅ تم النسخ الاحتياطي الدوري")
    except Exception as e:
        logger.error(f"❌ خطأ في النسخ الاحتياطي: {e}")

# ===== النشر التلقائي =====
async def scheduled_post(context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    logger.info("⏰ بدء دورة النشر التلقائي")
    
    try:
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600, "post_counter": 0})
        current_counter = schedule_settings.get("post_counter", 0)
        should_post_image = (current_counter + 1) >= IMAGE_POST_INTERVAL
        
        channels_data = load_channels_data()
        if not channels_data:
            logger.warning("⚠️ لا توجد قنوات.")
            return
        
        all_quotes = await quotes_cache.get_all_quotes()
        if not all_quotes:
            logger.warning("⚠️ لا توجد اقتباسات.")
            return

        posted_quotes = load_json(POSTED_QUOTES_FILE, [])
        available_quotes = [q for q in all_quotes if q not in posted_quotes]

        if not available_quotes:
            logger.info("🔔 إعادة تعيين سجل الأذكار...")
            posted_quotes = []
            available_quotes = all_quotes

        message_text = random.choice(available_quotes)
        logger.info(f"💬 الاقتباس: {message_text[:50]}... | نوع المنشور: {'صورة' if should_post_image else 'نص'}")

        async def send_content(bot, chat_info: Dict, text: str, is_image: bool) -> bool:
            max_retries = 3 
            chat_id = int(chat_info["id"])
            
            for attempt in range(max_retries):
                try:
                    if is_image:
                        images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.png")) + list(IMAGES_DIR.glob("*.jpeg")) + list(IMAGES_DIR.glob("*.webp"))
                        if not images:
                            await bot.send_message(chat_id=chat_id, text=f"<blockquote>{escape(text)}</blockquote>", parse_mode="HTML")
                        else:
                            img = random.choice(images)
                            with open(img, 'rb') as photo:
                                await bot.send_photo(chat_id=chat_id, photo=photo, caption=text)
                    else:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"<blockquote>{escape(text)}</blockquote>",
                            parse_mode="HTML"
                        )
                    
                    update_fail_count(chat_info["id"], False)
                    return True 

                except Exception as e:
                    error_msg = str(e).lower()
                    logger.warning(f"⚠️ محاولة {attempt + 1} فشلت للقناة {chat_id}: {e}")
                    
                    if "forbidden" in error_msg or "bot was blocked" in error_msg:
                        break
                    
                    if attempt == max_retries - 1:
                        update_fail_count(chat_info["id"], True)
                        return False
                    
                    await asyncio.sleep(2)
            
            return False

        tasks = [send_content(context.bot, item, message_text, should_post_image) for item in channels_data]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if isinstance(r, bool) and r)

        if should_post_image:
            schedule_settings["post_counter"] = 0
        else:
            schedule_settings["post_counter"] = current_counter + 1
        
        save_json(SCHEDULE_FILE, schedule_settings)

        posted_quotes.append(message_text)
        if len(posted_quotes) > MAX_POSTED_QUOTES:
            posted_quotes = posted_quotes[-MAX_POSTED_QUOTES:]
        save_json(POSTED_QUOTES_FILE, posted_quotes)

        elapsed = time.time() - start_time
        logger.info(f"✅ اكتمل النشر: {success_count}/{len(channels_data)} (العداد: {schedule_settings['post_counter']}) في {elapsed:.2f} ثانية")

    except Exception as e:
        logger.error(f"❌ خطأ في النشر التلقائي: {e}", exc_info=True)

# ===== تبديل الجدولة =====
async def toggle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600, "post_counter": 0})
    new_state = not schedule_settings.get("enabled", False)
    schedule_settings["enabled"] = new_state
    
    if not save_json(SCHEDULE_FILE, schedule_settings):
        await update.callback_query.answer("❌ فشل الحفظ!", show_alert=True)
        return
    
    job_queue = context.application.job_queue
    if job_queue:
        current_jobs = job_queue.get_jobs_by_name("scheduled_post")
        for job in current_jobs:
            job.schedule_removal()
    
    if new_state and job_queue:
        interval = schedule_settings.get("interval", 3600)
        job_queue.run_repeating(scheduled_post, interval=interval, first=10, name="scheduled_post")
        await update.callback_query.answer(f"✅ تم التفعيل كل {interval//60} دقيقة", show_alert=True)
    elif not new_state:
        await update.callback_query.answer("❌ تم الإيقاف", show_alert=True)
    
    await start(update, context)

# ===== تعيين الفاصل =====
async def set_schedule_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        interval_minutes = int(update.message.text)
        if not 1 <= interval_minutes <= 1440:
            await update.message.reply_text("❌ الفاصل يجب أن يكون بين 1-1440 دقيقة!")
            return
        
        interval_seconds = interval_minutes * 60
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600, "post_counter": 0})
        schedule_settings["interval"] = interval_seconds
        save_json(SCHEDULE_FILE, schedule_settings)
        
        await update.message.reply_text(f"✅ تم تعيين الفاصل إلى {interval_minutes} دقيقة")
        
        job_queue = context.application.job_queue
        if schedule_settings.get("enabled") and job_queue:
            current_jobs = job_queue.get_jobs_by_name("scheduled_post")
            for job in current_jobs:
                job.schedule_removal()
            job_queue.run_repeating(scheduled_post, interval=interval_seconds, first=10, name="scheduled_post")
            
    except ValueError:
        await update.message.reply_text("❌ أرسل رقماً فقط!")
    
    await start(update, context)
    
# ===== إدارة القنوات =====
async def manage_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels_data = load_channels_data()
    if not channels_data:
        await update.callback_query.edit_message_text("❌ لا توجد قنوات.")
        return

    keyboard = []
    for item in channels_data[:50]:
        try:
            chat = await context.bot.get_chat(int(item["id"]))
            title = chat.title[:25] if chat.title else item["title"]
        except:
            title = f"غير معروف ({item['id'][-8:]})"
        
        fails = item.get("fails", 0)
        status_emoji = "❌" if fails > 0 else "✅"
        type_emoji = "📢" if item["type"] == "channel" else "👥"
        
        keyboard.append([InlineKeyboardButton(f"{type_emoji} {status_emoji} {title}", callback_data=f"remove_chat_{item['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    await update.callback_query.edit_message_text(f"القنوات والمجموعات (اضغط للحذف):", reply_markup=InlineKeyboardMarkup(keyboard))

async def remove_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    if remove_chat_from_data(chat_id):
        await update.callback_query.answer("✅ تم الحذف", show_alert=True)
        logger.info(f"✓ حذف {chat_id}")
    else:
        await update.callback_query.answer("⚠️ لم يتم العثور", show_alert=True)
    await manage_channels_menu(update, context)

# ===== تحميل المهام =====
def load_scheduled_jobs(job_queue: JobQueue):
    try:
        schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600, "post_counter": 0})
        if schedule_settings.get("enabled"):
            interval = schedule_settings.get("interval", 3600)
            job_queue.run_repeating(scheduled_post, interval=interval, first=10, name="scheduled_post")
            logger.info(f"✅ تم تحميل job النشر كل {interval/60:.1f} دقيقة")
        
        # تشغيل النسخ الاحتياطي كل 6 ساعات (21600 ثانية)
        job_queue.run_repeating(backup_job, interval=21600, first=60, name="backup_job")
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل الجدولة: {e}")

# ===== التشغيل =====
def main():
    logger.info("🚀 بدء تشغيل البوت...")
    logger.info(f"👨‍💼 ADMIN_ID: {ADMIN_ID}")

    schedule_settings = load_json(SCHEDULE_FILE, {"enabled": False, "interval": 3600, "post_counter": 0})
    logger.info(f"📊 النشر التلقائي: {'مفعل' if schedule_settings.get('enabled') else 'معطل'}")

    channels_data = load_channels_data()
    logger.info(f"📢 عدد القنوات: {len(channels_data)}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_error_handler(error_handler)

    load_scheduled_jobs(app.job_queue)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.User(ADMIN_ID), handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("✅ البوت جاهز...")

    # تمت إزالة المراقب (Watchdog) وعدم وجود حلقة while True
    # البوت يعمل كعملية واحدة موجهة للاستضافة
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
