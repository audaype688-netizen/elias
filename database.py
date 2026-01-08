# database.py
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import config

# إعداد المحرك والقاعدة
engine = create_engine(f'sqlite:///{config.DB_NAME}', echo=False)
Base = declarative_base()
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(50))
    is_admin = Column(Boolean, default=False)

class Channel(Base):
    __tablename__ = 'channels'
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, nullable=False)
    title = Column(String(100))
    added_by = Column(Integer, ForeignKey('users.user_id')) # من أضافها
    category = Column(String(50)) # حب، عيد ميلاد، إلخ
    msg_format = Column(String(20), default='normal') # blockquote or normal
    is_active = Column(Boolean, default=True)

class AdminLog(Base):
    __tablename__ = 'admin_logs'
    id = Column(Integer, primary_key=True)
    action = Column(String(100)) # نوع الحدث (قناة جديدة، مشرف جديد)
    details = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class FileContent(Base):
    __tablename__ = 'file_content'
    id = Column(Integer, primary_key=True)
    category = Column(String(50)) # القسم التابع له
    content = Column(Text, nullable=False) # نص الاقتباس
    last_used_index = Column(Integer, default=0) # مؤقت لمنع التكرار (سنستخدم خوارزمية دورية)

class BotSettings(Base):
    __tablename__ = 'bot_settings'
    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True)
    value = Column(String(200)) # القيمة (مثلاً: on/off لتفعيل النشر)

# إنشاء الجداول
Base.metadata.create_all(engine)

# دوال مساعدة لقاعدة البيانات
def add_user(user_id, username=None):
    session = Session()
    user = session.query(User).filter_by(user_id=user_id).first()
    if not user:
        user = User(user_id=user_id, username=username)
        session.add(user)
        session.commit()
    session.close()

def is_admin(user_id):
    session = Session()
    # المطور دائماً أدمن
    if user_id == config.DEVELOPER_ID:
        session.close()
        return True
    user = session.query(User).filter_by(user_id=user_id).first()
    res = user.is_admin if user else False
    session.close()
    return res

def add_channel(channel_id, title, added_by, category, msg_format):
    session = Session()
    try:
        ch = Channel(channel_id=channel_id, title=title, added_by=added_by, category=category, msg_format=msg_format)
        session.add(ch)
        session.commit()
        return True
    except:
        session.rollback()
        return False
    finally:
        session.close()

def get_active_channels():
    session = Session()
    channels = session.query(Channel).filter_by(is_active=True).all()
    session.close()
    return channels

def add_file_content(category, texts_list):
    session = Session()
    count = 0
    for text in texts_list:
        # يمكن إضافة تحقق بسيط لعدم التكرار هنا، لكن الطلب كان عدم التكرار في النشر
        new_content = FileContent(category=category, content=text.strip())
        session.add(new_content)
        count += 1
    session.commit()
    session.close()
    return count

def get_next_content(category):
    """
    هذه الدالة تجلب النص التالي بحيث لا يتكرر حتى تنتهي القائمة
    """
    session = Session()
    # جلب كل المحتوى للقسم
    all_content = session.query(FileContent).filter_by(category=category).all()
    session.close()
    
    if not all_content:
        return None
        
    # خوارزمية بسيطة للتأكد من الدوران: نحتفظ بمؤشر عام في ملف الإعدادات لكل قسم
    # أو نستخدم حقل last_used_index إذا تم تحديثه.
    # للتبسيط والأداء: سنستخدم طريقة قائمة في الذاكرة للنشر المتتابع
    # لكن بما أننا نريد "عدم حذف القديم"، سنقوم بتحديث الـ last_used_index في القاعدة
    
    session = Session()
    try:
        # نقوم بتحميل العناصر واختيار العنصر الذي لم يتم استخدامه مؤخراً
        # هنا سنقوم بتحسين الأداء: نجلب العنصر الذي يحمل أقل قيمة last_used_index
        
        # تعديل: لكي لا نعقد الأمر، سنستخدم استراتيجية بسيطة للنشر الدوري
        # نجلب جميع العناصر
        content_list = [c.content for c in all_content]
        
        # نجلب آخر مؤشر تم استخدامه لهذا القسم من إعدادات البوت (أو نحسبه)
        # لنقم بتخزين المؤشر في جدول BotSettings
        setting = session.query(BotSettings).filter_by(key=f'index_{category}').first()
        current_index = 0
        if setting:
            current_index = int(setting.value)
        
        if current_index >= len(content_list):
            current_index = 0 # إعادة البدء
            
        selected_text = content_list[current_index]
        
        # تحديث المؤشر
        if setting:
            setting.value = str(current_index + 1)
        else:
            session.add(BotSettings(key=f'index_{category}', value=str(current_index + 1)))
            
        session.commit()
        return selected_text
    except Exception as e:
        print(f"Error getting content: {e}")
        session.rollback()
        return None
    finally:
        session.close()

def log_action(action, details):
    session = Session()
    log = AdminLog(action=action, details=details)
    session.add(log)
    session.commit()
    session.close()

def remove_channel_db(channel_id):
    session = Session()
    try:
        ch = session.query(Channel).filter_by(channel_id=channel_id).first()
        if ch:
            session.delete(ch)
            session.commit()
            return True
    except:
        pass
    finally:
        session.close()
    return False

def get_stats():
    session = Session()
    users_count = session.query(User).count()
    channels_count = session.query(Channel).count()
    
    categories = ['حب', 'عيد ميلاد', 'اقتباسات عامة', 'ابيات شعرية']
    stats_text = f"📊 **إحصائيات البوت**\n\n👥 عدد الأعضاء: {users_count}\n📢 عدد القنوات/المجموعات: {channels_count}\n\n📁 **عدد الاقتباسات لكل قسم:**\n"
    
    for cat in categories:
        count = session.query(FileContent).filter_by(category=cat).count()
        stats_text += f"• {cat}: {count}\n"
        
    session.close()
    return stats_text