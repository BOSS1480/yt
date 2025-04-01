import os
import logging
import asyncio
import time
import re
import math
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import yt_dlp
import requests
from PIL import Image
from io import BytesIO
from flask import Flask

# פרטי התחברות לבוט
API_ID = ''         # הכנס כאן את ה-API ID שלך
API_HASH = ''       # הכנס כאן את ה-API HASH שלך
TELEGRAM_TOKEN = '' # הכנס כאן את הטוקן של הבוט

# הגבלת קובץ עד 2 ג'יגה
MAX_FILESIZE = 2 * 1024 * 1024 * 1024  # 2 ג'יגה בבתים

# שימוש בקובץ cookies.txt עבור yt-dlp
COOKIES_FILE = 'cookies.txt'

# יצירת תיקיות נדרשות
for folder in ['downloads', 'thumbnails']:
    if not os.path.exists(folder):
        os.makedirs(folder)

# הגדרת Pyrogram Client
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=TELEGRAM_TOKEN)

def format_size(size):
    if size == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f"{s} {size_name[i]}"

def format_time(seconds):
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}m {seconds}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours}h {minutes}m {seconds}s"

def download_thumbnail(url, video_id):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            thumbnail_path = f'thumbnails/{video_id}.jpg'
            img.save(thumbnail_path, 'JPEG')
            return thumbnail_path
    except Exception as e:
        logging.error(f"Error downloading thumbnail: {str(e)}")
    return None

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

async def upload_progress(current, total, message, title):
    progress = min(100, round(current * 100 / total))
    progress_bar = "█" * int(progress/5) + "░" * (20 - int(progress/5))
    status_text = (
        f"🎵 {title}\n\n"
        f"⬆️ מעלה: {progress}%\n"
        f"[{progress_bar}]\n"
        f"💾 {format_size(current)}/{format_size(total)}\n"
    )
    try:
        await message.edit_text(status_text)
    except Exception as e:
        logging.error(f"Error updating progress: {str(e)}")

async def download_and_send_media(client, message, url, as_audio=False):
    status_message = None
    downloaded_file = None
    thumbnail_path = None

    try:
        status_message = await message.reply_text("🔍 מאחזר מידע...")

        # הגדרת אפשרויות yt-dlp כולל הגבלת גודל ושימוש ב-cookies.txt
        ydl_opts = {
            'format': 'bestaudio/best' if as_audio else 'bestvideo[ext=mp4]+bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'max_filesize': MAX_FILESIZE,
            'cookiefile': COOKIES_FILE,
        }

        if as_audio:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]

        # קבלת מידע על המדיה
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            original_title = info.get('title', 'Media')
            title = sanitize_filename(original_title)
            video_id = info.get('id', '')
            duration = info.get('duration', 0)
            thumbnail_url = info.get('thumbnail')
            if thumbnail_url:
                thumbnail_path = download_thumbnail(thumbnail_url, video_id)

        await status_message.edit_text("⬇️ מתחיל הורדה...")
        # הורדת הקובץ
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        file_extension = 'mp3' if as_audio else 'mp4'
        original_downloaded_file = f"downloads/{video_id}.{file_extension}"
        downloaded_file = f"downloads/{title}.{file_extension}"
        if os.path.exists(original_downloaded_file):
            os.rename(original_downloaded_file, downloaded_file)

        await status_message.edit_text("⬆️ מעלה לטלגרם...")
        if as_audio:
            msg = await client.send_audio(
                message.chat.id,
                downloaded_file,
                title=original_title,
                duration=duration,
                thumb=thumbnail_path,
                caption=f"🎵 {original_title}",
                progress=lambda current, total: upload_progress(current, total, status_message, original_title)
            )
        else:
            msg = await client.send_video(
                message.chat.id,
                downloaded_file,
                caption=f"🎬 {original_title}",
                duration=duration,
                thumb=thumbnail_path,
                supports_streaming=True,
                progress=lambda current, total: upload_progress(current, total, status_message, original_title)
            )

        await status_message.edit_text("✅ הועלה בהצלחה!")
        await asyncio.sleep(5)
        await status_message.delete()

    except Exception as e:
        error_message = f"❌ שגיאה: {str(e)}"
        if status_message:
            await status_message.edit_text(error_message)
        else:
            await message.reply_text(error_message)
    finally:
        try:
            if downloaded_file and os.path.exists(downloaded_file):
                os.remove(downloaded_file)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
        except Exception as e:
            logging.error(f"Error cleaning up files: {str(e)}")

# פקודת /d לקבלת קישור והצגת אפשרות בחירה בין וידאו לשמע
@app.on_message(filters.command("d"))
async def download_command(client, message):
    if len(message.command) < 2:
        await message.reply_text(
            "📝 שימוש: /d [קישור ליוטיוב]\n"
            "לדוגמה: /d https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        return

    url = message.command[1]
    if not ('youtube.com' in url or 'youtu.be' in url):
        await message.reply_text("❌ אנא שלח קישור תקין של יוטיוב")
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 וידאו", callback_data=f"video_{url}"),
            InlineKeyboardButton("🎵 שמע", callback_data=f"audio_{url}")
        ]
    ])

    await message.reply_text("🔽 בחר את סוג ההורדה:", reply_markup=keyboard)

# טיפול בבחירת המשתמש מהאינליין
@app.on_callback_query(filters.regex(r"^(video|audio)_"))
async def download_callback(client, callback_query):
    download_type, url = callback_query.data.split("_", 1)
    await callback_query.message.delete()
    await download_and_send_media(
        client,
        callback_query.message,
        url,
        as_audio=(download_type == "audio")
    )

# יצירת שרת Flask קטן עבור Health Check (נדרש ב-Koyeb)
flask_app = Flask("healthcheck")

@flask_app.route("/")
def index():
    return "Bot is running", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # הפעלת שרת Flask במקביל לבוט
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    app.run()
