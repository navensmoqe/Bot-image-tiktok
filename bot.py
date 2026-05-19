import os
import json
import requests
import textwrap
from io import BytesIO
from urllib.parse import quote
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# --- إعدادات البيئة ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL") # رابط التطبيق الذي يوفره Render تلقائياً
PORT = int(os.environ.get("PORT", "8443"))

# --- إعداد جيميناي ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

PROMPT_TEMPLATE = """
أنت صانع محتوى محترف على تيك توك. مهمتك تحويل المقال التالي إلى شرائح قصيرة لتطبيق تيك توك.
الشروط:
1. حافظ على الفكرة الأصلية 100%.
2. الأسلوب تفاعلي وجذاب.
3. نص كل شريحة قصير (10-20 كلمة كحد أقصى).
4. وصف بصري بالإنجليزي لكل شريحة يضاف له (vertical, aesthetic background, no text).
5. أخرج النتيجة حصرياً بصيغة JSON كالتالي دون أي نصوص أخرى:
[
  {
    "slide_text": "النص العربي",
    "image_prompt": "English description"
  }
]
المقال:
{text}
"""

def clean_json(text):
    text = text.strip()
    if text.startswith("
http://googleusercontent.com/immersive_entry_chip/0
http://googleusercontent.com/immersive_entry_chip/1
http://googleusercontent.com/immersive_entry_chip/2

---

### 2. خطوات الرفع على منصة GitHub
1. قم بإنشاء حساب على [GitHub](https://github.com/) إذا لم يكن لديك واحد.
2. اضغط على الزر الأخضر **"New"** لإنشاء مستودع جديد (Repository).
3. قم بتسميته (مثلاً: `tiktok-ai-bot`)، واجعله **Private** (خاص) للحفاظ على كودك آمناً.
4. ارفع الملفات الثلاثة (`bot.py`، `requirements.txt`، `font.ttf`) إلى المستودع عبر سحبها وإفلاتها في المتصفح، ثم اضغط على **Commit changes**.

---

### 3. خطوات التثبيت والتشغيل على منصة Render
1. سجل دخولك إلى منصة [Render](https://render.com/) واربط حسابك بـ GitHub.
2. من لوحة التحكم، اضغط على **"New +"** واختر **"Web Service"**.
3. اختر المستودع الخاص بك (`tiktok-ai-bot`) واضغط على **Connect**.
4. قم بإعداد الخصائص التالية في صفحة الإعدادات:
   * **Name:** اختر أي اسم (مثلاً: `my-tiktok-bot-123`).
   * **Language:** تأكد من اختيار **Python**.
   * **Start Command:** اكتب الأمر: `python bot.py`
5. انزل للأسفل إلى قسم **Environment Variables** (المتغيرات البيئية) واضغط على **Add Environment Variable** مرتين لإضافة القيم التالية:
   * المفتاح الأول: `TELEGRAM_TOKEN` | القيمة: (ضع هنا توكن البوت الذي حصلت عليه من BotFather).
   * المفتاح الثاني: `GEMINI_API_KEY` | القيمة: (ضع هنا مفتاح API الخاص بك من Google AI Studio).
6. اضغط على زر **Create Web Service** في أسفل الصفحة.

سيقوم Render الآن بتثبيت المكتبات، وقراءة التوكن الخاص بك، وربط البوت مباشرةً بتيليجرام عبر رابط الويب (Webhook). بمجرد أن تظهر كلمة **"Live"** باللون الأخضر في منصة Render، يمكنك فتح تيليجرام وإرسال أي مقال لبوتك ليعمل بكفاءة.
