import asyncio
import random
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient
import os
import logging
import sys
import feedparser

# إعداد نظام تسجيل الأخطاء
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_log.txt"),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- إعدادات التليجرام (يجب تعبئتها) ---
API_ID = "6825462"
API_HASH = "3b3cb233c159b6f48798e10c4b5fdc83"
PHONE = "+967715022093"
CHANNEL_USERNAME = "jxxxi"

DB_FILE = 'published_quotes.txt'

def load_published():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f)
    return set()

def save_published(quote):
    with open(DB_FILE, 'a', encoding='utf-8') as f:
        f.write(quote[:100] + '\n') # نحفظ أول 100 حرف للتحقق

async def fetch_from_web():
    """جلب اقتباسات من مصادر متنوعة على الإنترنت"""
    quotes = []
    
    # المصدر 1: RSS من مدونات أدبية (مثال)
    rss_urls = [
        'https://muhlhel.wordpress.com/feed/',
        'https://salehabonaji.wordpress.com/feed/'
    ]
    
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                # تنظيف النص من وسوم HTML
                soup = BeautifulSoup(entry.summary if 'summary' in entry else entry.title, 'html.parser')
                text = soup.get_text().strip()
                if len(text) > 20 and len(text) < 300:
                    quotes.append(text)
        except:
            continue

    # المصدر 2: محاكاة جلب من مواقع حكم واقتباسات (Scraping بسيط)
    # ملاحظة: في الواقع يفضل استخدام APIs أو RSS لضمان الاستقرار
    # سنضيف هنا قائمة احتياطية كبيرة جداً لضمان التنوع في حال فشل المواقع
    backup_quotes = [
        "أنت النبض الذي لا يتوقف في قلبي.",
        "في عيونك أرى حياة كاملة لم أعشها بعد.",
        "أحبك في كل ثانية ألف عام.",
        "أنت أجمل ما حدث لي في 2026.",
        "وجودك بجانبي هو جنتي على الأرض.",
        "كل كلمات الغزل لا تكفي لوصف عينيك.",
        "أنت القصيدة التي يعجز الشعراء عن كتابتها.",
        "نبض قلبي يناديك في كل حين.",
        "أنت لست مجرد حلم، أنت واقعي الأجمل.",
        "سأبقى أحبك حتى يشيخ الزمان."
    ]
    
    return quotes if quotes else backup_quotes

async def post_romantic_quote(client):
    logging.info("جاري البحث عن نبضة حب جديدة من الإنترنت...")
    published = load_published()
    
    # جلب محتوى جديد
    online_quotes = await fetch_from_web()
    
    # تصفية المحتوى المنشور سابقاً
    available = [q for q in online_quotes if q[:100] not in published]
    
    if not available:
        # إذا لم نجد جديداً، نستخدم عينة عشوائية
        available = online_quotes

    quote = random.choice(available)
    
    #message = f"✨ **نبضة حب متجددة** ✨\n\n"
    message = f"```"
    message += f"نبض | Nabd"
    message += f"```"
    message += f"“ {quote} ”\n\n."
    
    
    try:
        await client.send_message(CHANNEL_USERNAME, message)
        save_published(quote)
        logging.info(f"تم النشر بنجاح: {quote[:30]}...")
    except Exception as e:
        logging.error(f"خطأ في النشر: {e}")

async def main():
    logging.info("جاري تشغيل بوت نبض المتصل بالإنترنت...")
    
    if API_ID == 'YOUR_API_ID' or API_HASH == 'YOUR_API_HASH':
        logging.error("خطأ: يجب تعبئة API_ID و API_HASH!")
        return

    try:
        client = TelegramClient('nabd_session', API_ID, API_HASH)
        await client.start(PHONE)
        logging.info("البوت متصل ويعمل الآن!")
        
        while True:
            await post_romantic_quote(client)
            # النشر كل 3 ساعات لضمان التجدد
            logging.info("تم النشر. الانتظار لمدة 3 ساعات...")
            await asyncio.sleep(10800) 
            
    except Exception as e:
        logging.critical(f"فشل تشغيل البوت: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("تم إيقاف البوت.")
