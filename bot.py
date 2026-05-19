import os
import json
import requests
import textwrap
import logging
import urllib.request
from io import BytesIO
from urllib.parse import quote
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# --- إعداد سجلات الأخطاء ---
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

# --- تحميل الخط العربي تلقائياً (الحل السحري) ---
FONT_PATH = "cairo_arabic.ttf"
if not os.path.exists(FONT_PATH):
    logger.info("جاري تحميل خط Cairo العربي...")
    try:
        font_url = "https://github.com/google/fonts/raw/main/ofl/cairo/Cairo-Bold.ttf"
        urllib.request.urlretrieve(font_url, FONT_PATH)
        logger.info("تم تحميل الخط بنجاح.")
    except Exception as e:
        logger.error(f"فشل تحميل الخط: {e}")

# --- إعداد عميل Groq ---
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

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
    text = text.strip()
    if text.startswith("```json"): 
        text = text[7:]
    if text.startswith("```"): 
        text = text[3:]
    if text.endswith("```"): 
        text = text[:-3]
    return text.strip()

def create_image_with_text(image_bytes, arabic_text):
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    
    # تظليل الصورة لبروز النص
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 140))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    
    # استخدام الخط العربي الذي تم تحميله
    try:
        font = ImageFont.truetype(FONT_PATH, 60)
    except IOError:
        font = ImageFont.load_default()

    # تقسيم وتوسيط النص
    lines = textwrap.wrap(arabic_text, width=25)
    y_text = (img.height - (len(lines) * 80)) / 2
    
    for line in lines:
        # معالجة وتقويم الحروف العربية
        reshaped = arabic_reshaper.reshape(line)
        bidi = get_display(reshaped)
        
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
    msg = await update.message.reply_text("⏳ جاري تحليل النص عبر Groq...")
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": PROMPT_TEMPLATE.format(text=user_text),
                }
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        
        response_text = chat_completion.choices[0].message.content
        json_data = json.loads(clean_json(response_text))
        slides = json_data.get("slides", [])
        
        await msg.edit_text("🎨 جاري توليد الصور ورسم النصوص فوقها...")
        
        media_group = []
        for slide in slides:
            safe_prompt = quote(slide['image_prompt'])
            
            base_domain = "https://" + "image.pollinations.ai"
            img_url = f"{base_domain}/prompt/{safe_prompt}?width=1080&height=1920&nologo=true"
            
            img_response = requests.get(img_url)
            
            if img_response.status_code == 200:
                final_image = create_image_with_text(img_response.content, slide['slide_text'])
                media_group.append(InputMediaPhoto(final_image))
        
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
        logger.error("خطأ حرج: تأكد من إضافة TELEGRAM_TOKEN و GROQ_API_KEY!")
        return
        
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_text))
    
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=RENDER_URL
    )

if __name__ == "__main__":
    main()
