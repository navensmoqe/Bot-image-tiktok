import os
import json
import requests
import textwrap
import logging
from io import BytesIO
from urllib.parse import quote
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# --- إعداد سجلات الأخطاء (Logging) ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- إعدادات البيئة ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PORT = int(os.environ.get("PORT", "8443"))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://bot-image-tiktok.onrender.com")

# --- إعداد عميل Groq ---
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

# --- أمر التوجيه (Prompt) ---
# تم استخدام الأقواس المزدوجة {{ }} لكي لا تتداخل مع دالة format في بايثون
PROMPT_TEMPLATE = """
أنت صانع محتوى محترف على تيك توك. مهمتك تحويل المقال التالي إلى شرائح قصيرة لتطبيق تيك توك.
الشروط:
1. حافظ على الفكرة الأصلية 100%.
2. الأسلوب تفاعلي وجذاب.
3. نص كل شريحة قصير (10-20 كلمة كحد أقصى).
4. وصف بصري بالإنجليزي لكل شريحة يضاف له (vertical, aesthetic background, no text).
5. أخرج النتيجة حصرياً بصيغة JSON تحتوي على مفتاح "slides" كالتالي دون أي نصوص أخرى:
{{
  "slides": [
    {{
      "slide_text": "النص العربي هنا",
      "image_prompt": "English description here"
    }}
  ]
}}

المقال:
{text}
"""

def clean_json(text):
    """تنظيف النص من علامات الماركداون إذا قام الذكاء الاصطناعي بإضافتها"""
    text = text.strip()
    if text.startswith("```json"): 
        text = text[7:]
    if text.startswith("```"): 
        text = text[3:]
    if text.endswith("```"): 
        text = text[:-3]
    return text.strip()

def create_image_with_text(image_bytes, arabic_text):
    """دمج النص العربي مع الصورة"""
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    
    # طبقة تظليل سوداء شفافة لتوضيح النص
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 140))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    
    # تحميل الخط العربي
    try:
        font = ImageFont.truetype("font.ttf", 60)
    except IOError:
        logger.warning("ملف الخط font.ttf غير موجود، سيتم استخدام الخط الافتراضي.")
        font = ImageFont.load_default()

    # تقسيم النص الطويل إلى أسطر
    lines = textwrap.wrap(arabic_text, width=25)
    y_text = (img.height - (len(lines) * 80)) / 2
    
    for line in lines:
        # معالجة الحروف العربية
        reshaped = arabic_reshaper.reshape(line)
        bidi = get_display(reshaped)
        
        # التوسيط
        bbox = draw.textbbox((0, 0), bidi, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((img.width - w) / 2, y_text), bidi, font=font, fill=(255, 255, 255, 255))
        y_text += 80
        
    out_bytes = BytesIO()
    img.convert("RGB").save(out_bytes, format="JPEG")
    out_bytes.seek(0)
    return out_bytes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! أرسل لي أي مقال وسأحوله إلى سلسلة صور جاهزة لتيك توك 🚀")

async def process_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    msg = await update.message.reply_text("⏳ جاري تحليل النص وصياغته باستخدام Groq...")
    
    try:
        # استدعاء Groq API
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": PROMPT_TEMPLATE.format(text=user_text),
                }
            ],
            model="llama3-70b-8192", # استخدام أقوى نموذج من Llama3
            response_format={"type": "json_object"} # إجبار النموذج على إرجاع JSON نظيف
        )
        
        response_text = chat_completion.choices[0].message.content
        json_data = json.loads(clean_json(response_text))
        slides = json_data.get("slides", [])
        
        await msg.edit_text("🎨 جاري توليد الصور ورسم النصوص فوقها...")
        
        media_group = []
        for slide in slides:
            # طلب الصورة من Pollinations
            safe_prompt = quote(slide['image_prompt'])
            img_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){safe_prompt}?width=1080&height=1920&nologo=true"
            img_response = requests.get(img_url)
            
            if img_response.status_code == 200:
                final_image = create_image_with_text(img_response.content, slide['slide_text'])
                media_group.append(InputMediaPhoto(final_image))
        
        # إرسال ألبوم الصور
        if media_group:
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
            await msg.delete()
        else:
            await msg.edit_text("حدث خطأ أثناء تحميل الصور من المصدر.")
            
    except Exception as e:
        logger.error(f"Error processing text: {e}")
        await msg.edit_text("عذراً، حدث خطأ أثناء المعالجة. يرجى التأكد من النص والمحاولة مجدداً.")

def main():
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        logger.error("خطأ حرج: تأكد من إضافة TELEGRAM_TOKEN و GROQ_API_KEY في منصة Render!")
        return
        
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_text))
    
    # تشغيل البوت بنظام Webhook ليتوافق مع منصة Render
    logger.info(f"جاري تشغيل Webhook على الرابط: {RENDER_URL}")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=RENDER_URL
    )

if __name__ == "__main__":
    main()
