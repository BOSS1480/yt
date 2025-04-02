import os
import logging
import asyncio
import time
import re
import math
from datetime import datetime
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import yt_dlp
import requests
from PIL import Image
from io import BytesIO
import humanize

# הגדרות התחברות – הכנסו את הפרטים שלכם
API_ID = '22558238'
API_HASH = '41abc14dd9f760887a50f9cd2cc1bb73'
TELEGRAM_TOKEN = '7349147675:AAFhc6DljIe6cpRhGB6oUM1x2szOcuhWrhs'

# הגבלת גודל קובץ: 2 ג'יגה = 2147483648 בתים
MAX_FILESIZE = 2147483648

# יצירת תיקיות נדרשות
for folder in ['downloads', 'thumbnails']:
    if not os.path.exists(folder):
        os.makedirs(folder)

# ודאו שקיים קובץ cookies.txt בתיקייה הראשית
if not os.path.exists("cookies.txt"):
    open("cookies.txt", "w").close()

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

async def update_progress(message, title, current, total, start_time, upload=False):
    progress = min(100, round(current * 100 / total))
    progress_bar = "█" * int(progress/5) + "░" * (20 - int(progress/5))
    elapsed_time = time.time() - start_time
    speed = current / elapsed_time if elapsed_time > 0 else 0
    remaining = total - current
    eta = format_time(int(remaining / speed)) if speed > 0 else "מחשב..."
    action = "⬆️ מעלה" if upload else "⬇️ מוריד"
    status_text = (
        f"🎵 {title}\n\n"
        f"{action}: {progress}%\n"
        f"[{progress_bar}]\n"
        f"⚡️ מהירות: {format_size(speed)}/s\n"
        f"💾 {format_size(current)}/{format_size(total)}\n"
        f"⏱ זמן שנותר: {eta}\n\n"
        f"❌ /cancel להפסקת ההורדה"
    )
    try:
        await message.edit_text(status_text)
    except Exception as e:
        logging.error(f"Error updating progress: {str(e)}")

async def download_and_send_media(client, message, url, mode, quality):
    """
    mode: "audio" או "video"
    quality: עבור וידאו – "1080", "720", "480"
             עבור שמע – "320" או "128"
    """
    status_message = None
    downloaded_file = None
    thumbnail_path = None
    try:
        status_message = await message.reply_text("🔍 מאחזר מידע מהיוטיוב...")

        # הגדרת אפשרויות yt-dlp בסיסיות
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'max_filesize': MAX_FILESIZE,
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'cookiefile': 'cookies.txt'
        }
        if mode == "audio":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality,
            }]
        else:
            ydl_opts['format'] = f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

        def progress_hook(d):
            if d['status'] == 'downloading':
                current = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total:
                    asyncio.run_coroutine_threadsafe(
                        update_progress(status_message, info.get('title', 'Media'), current, total, start_time),
                        client.loop
                    )
            elif d['status'] == 'finished':
                asyncio.run_coroutine_threadsafe(
                    status_message.edit_text("✅ הורדה הושלמה, מתחיל העלאה..."),
                    client.loop
                )

        ydl_opts['progress_hooks'] = [progress_hook]
        start_time = time.time()
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
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        ext = 'mp3' if mode == "audio" else 'mp4'
        original_downloaded_file = f"downloads/{video_id}.{ext}"
        downloaded_file = f"downloads/{title}.{ext}"
        if os.path.exists(original_downloaded_file):
            os.rename(original_downloaded_file, downloaded_file)

        start_time_upload = time.time()
        if mode == "audio":
            sent_msg = await client.send_audio(
                message.chat.id,
                downloaded_file,
                title=original_title,
                duration=duration,
                thumb=thumbnail_path,
                caption=f"🎵 {original_title}",
                progress=lambda current, total: asyncio.run(update_progress(status_message, original_title, current, total, start_time_upload, upload=True))
            )
        else:
            sent_msg = await client.send_video(
                message.chat.id,
                downloaded_file,
                caption=f"🎬 {original_title}",
                duration=duration,
                thumb=thumbnail_path,
                supports_streaming=True,
                progress=lambda current, total: asyncio.run(update_progress(status_message, original_title, current, total, start_time_upload, upload=True))
            )
        await status_message.edit_text("✅ העלאה הושלמה!")
        await asyncio.sleep(5)
        await status_message.delete()

    except Exception as e:
        err_text = f"❌ שגיאה: {str(e)}"
        if status_message:
            await status_message.edit_text(err_text)
        else:
            await message.reply_text(err_text)
    finally:
        try:
            if downloaded_file and os.path.exists(downloaded_file):
                os.remove(downloaded_file)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
        except Exception as e:
            logging.error(f"Error cleaning up files: {str(e)}")

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    welcome_text = (
        "שלום!\n\n"
        "אני בוט להורדת שירים וסרטונים מיוטיוב.\n"
        "שלחו לי קישור מיוטיוב ואני אשאל אתכם מה להוריד:\n"
        "וידאו (mp4) או שמע (mp3) ובאיזו איכות."
    )
    await message.reply_text(welcome_text)

@app.on_message(filters.text & ~filters.command() & filters.create(lambda _, __, msg: "youtu" in msg.text.lower()))
async def url_handler(client, message):
    url = message.text.strip()
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 וידאו", callback_data=f"mode_video|{url}"),
            InlineKeyboardButton("🎵 שמע", callback_data=f"mode_audio|{url}")
        ]
    ])
    await message.reply_text("בחרו מה להוריד:", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^mode_(video|audio)\|"))
async def mode_selection_callback(client, callback_query: CallbackQuery):
    data = callback_query.data.split("|")
    mode = data[0].split("_")[1]
    url = data[1]
    if mode == "video":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("1080p", callback_data=f"download|video|1080|{url}")],
            [InlineKeyboardButton("720p", callback_data=f"download|video|720|{url}")],
            [InlineKeyboardButton("480p", callback_data=f"download|video|480|{url}")]
        ])
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("320kbps", callback_data=f"download|audio|320|{url}")],
            [InlineKeyboardButton("128kbps", callback_data=f"download|audio|128|{url}")]
        ])
    await callback_query.message.delete()
    await callback_query.message.reply_text("בחרו איכות:", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^download\|(video|audio)\|(.*?)\|"))
async def download_callback(client, callback_query: CallbackQuery):
    parts = callback_query.data.split("|")
    mode = parts[1]
    quality = parts[2]
    url = parts[3]
    await callback_query.answer()
    await download_and_send_media(client, callback_query.message, url, mode, quality)

@app.on_message(filters.command("cancel"))
async def cancel_handler(client, message):
    await message.reply_text("ביטול הורדה – (פונקציונליות זו יכולה להיות מיושמת בהמשך)")

# הגדרת שרת HTTP פשוט עם aiohttp
from aiohttp import web

async def handle(request):
    return web.Response(text="Bot is running")

async def start_webserver():
    aio_app = web.Application()
    aio_app.router.add_get('/', handle)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()
    logging.info("Web server started on 0.0.0.0:8000")

async def main():
    await app.start()
    # הפעלת שרת HTTP במקביל
    asyncio.create_task(start_webserver())
    logging.info("Bot started")
    await idle()
    await app.stop()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())
