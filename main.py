import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from yt_dlp import YoutubeDL

# ==========================================
# 🔴 الإعدادات الأساسية (غيرها فقط)
TOKEN = '2073340985:AAFHC_df_iKwqfYh2L2fZLWp3Es8e_plgBA'  # ضع التوكن هنا
ADMINS = [778375826]        # ضع أيديك هنا لتلقي أخطاء البوت (اختياري)
# ==========================================

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)

# إنشاء الراوتر
router = Router()

# إنشاء مجلد التحميلات إذا لم يكن موجوداً
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==========================================
# ⚙️ إعدادات yt-dlp
# ==========================================

# خيارات تحميل الفيديو
ydl_opts_video = {
    'format': 'bestvideo+bestaudio/best', # دمج أفضل جودة فيديو مع أفضل صوت
    'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'merge_output_format': 'mp4',
}

# خيارات تحميل الصوت (MP3)
ydl_opts_audio = {
    'format': 'bestaudio/best',
    'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

# ==========================================
# 🧠 تحديد الحالات (States)
# ==========================================
class Form(StatesGroup):
    mode = State() # لتخزين الوضع: فيديو أو صوت

# ==========================================
# 🚀 المعالجات (Handlers)
# ==========================================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    # إنشاء الأزرار
    builder = InlineKeyboardBuilder()
    builder.button(text="🎥 فيديو (Video)", callback_data="set_mode_video")
    builder.button(text="🎵 صوت (Audio/MP3)", callback_data="set_mode_audio")
    builder.adjust(2) # جعل الأزرار بجانب بعضها
    
    await message.answer(
        "<b>أهلاً بك! 🤖</b>\n\n"
        "أرسل لي رابط من أي موقع وسأقوم بتحميله لك.\n"
        "اختر الوضع الافتراضي الآن:",
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(Form.mode)

# عند تغيير الوضع (الضغط على الأزرار)
@router.callback_query(F.data.startswith("set_mode_"))
async def set_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split("_")[-1] # video أو audio
    await state.update_data(mode=mode)
    
    mode_text = "فيديو 🎥" if mode == "video" else "صوت MP3 🎵"
    await callback.answer(f"تم تفعيل وضع {mode_text}")
    await callback.message.edit_text(f"✅ الوضع الحالي: <b>{mode_text}</b>\n\nأرسل الرابط الآن 👇", parse_mode=ParseMode.HTML)

# عند استقبال الرابط
@router.message(Form.mode, F.text)
async def process_link(message: Message, state: FSMContext):
    url = message.text
    data = await state.get_data()
    mode = data.get('mode', 'video') # الافتراضي فيديو
    
    # التحقق من الرابط
    if not url.startswith(("http://", "https://")):
        await message.answer("❌ الرابط غير صحيح، تأكد أنه يبدأ بـ http:// أو https://")
        return

    status_msg = await message.answer("⏳ <b>جاري الاتصال بالخادم...</b>", parse_mode=ParseMode.HTML)
    
    try:
        # اختيار الإعدادات حسب الوضع
        opts = ydl_opts_video if mode == 'video' else ydl_opts_audio
        file_ext = "mp4" if mode == 'video' else "mp3"
        file_type = "video" if mode == 'video' else "audio"

        # 1. جلب المعلومات (بدون تحميل) - لعدم تجميد البوت
        await status_msg.edit_text("🔍 <b>جاري جلب معلومات الفيديو...</b>", parse_mode=ParseMode.HTML)
        
        with YoutubeDL(opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            if info is None:
                await status_msg.edit_text("❌ فشل في العثور على الفيديو. تأكد أن الرابط صحيح.")
                return
            
            video_title = info.get('title', 'Video')
            video_id = info.get('id')
            filename = os.path.join(DOWNLOAD_DIR, f"{video_id}.{file_ext}")

            # التحقق من حجم الملف المقدر (اختياري)
            # info.get('filesize') قد يكون None أحياناً، لذا نتجاوزه إذا لم يوجد

        # 2. بدء التحميل الفعلي
        await status_msg.edit_text(f"⬇️ <b>جاري التحميل...</b>\n\n🎬 {video_title[:30]}...", parse_mode=ParseMode.HTML)
        
        with YoutubeDL(opts) as ydl:
            # تشغيل التحميل في خيط منفصل (Thread) لعدم تجميد البوت
            await asyncio.to_thread(ydl.download, [url])

        # 3. إرسال الملف
        if os.path.exists(filename):
            await status_msg.edit_text("🚀 <b>جاري الرفع إليك...</b>", parse_mode=ParseMode.HTML)
            
            file_size = os.path.getsize(filename)
            
            # التحقق من حد تليجرام (50 ميغا للمجاني)
            if file_size > 50 * 1024 * 1024:
                await message.answer(
                    f"⚠️ الملف كبير جداً ({file_size/(1024*1024):.1f} MB).\n"
                    "حسابات تليجرام المجانية لا تدعم إرسال ملفات أكبر من 50 ميغا.\n"
                    "يمكنك استخدام حساب بريميوم."
                )
            else:
                # إرسال كصوت أو فيديو
                with open(filename, 'rb') as f:
                    if mode == 'video':
                        await message.answer_video(f, caption=f"✅ {video_title}")
                    else:
                        await message.answer_audio(f, caption=f"✅ {video_title}")
            
            # 4. تنظيف (حذف الملف)
            os.remove(filename)
            await status_msg.delete() # حذف رسالة الحالة
            
        else:
            await status_msg.edit_text("❌ حدث خطأ: الملف لم يتم إنشاؤه.")

    except Exception as e:
        logging.error(f"Error: {e}")
        await status_msg.edit_text(f"❌ حدث خطأ غير متوقع:\n<code>{str(e)}</code>", parse_mode=ParseMode.HTML)

# ==========================================
# ▶️ التشغيل
# ==========================================
async def main():
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    # حذف الويب هوك القديم وتشغيل البولينغ
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ البوت يعمل الآن وجاهز لاستقبال الروابط!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⛔ تم إيقاف البوت.")
