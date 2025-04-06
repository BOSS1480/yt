import os
import subprocess
import requests
from yt_dlp import YoutubeDL
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatType
from flask import Flask, request

# הגדרות בסיסיות
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH")
COOKIES_FILE = 'cookies.txt'
STORAGE_CHANNEL_ID = int(os.environ.get("STORAGE_CHANNEL_ID"))

# הפעלת Pyrogram Client
app = Client(
    "youtube_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# הפעלת Flask
flask_app = Flask(__name__)

video_info_dict = {}


def escape_markdown(text):
    """מנקה תווים מיוחדים מהטקסט למניעת שגיאות בפרסור markdown"""
    if not text:
        return ""
    # מחליף מקף עם רווח במקף רגיל
    text = text.replace(' - ', ' - ')
    # מטפל בתווים מיוחדים
    special_chars = ['_', '"', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def download_thumbnail(url, filename):
    """מוריד תמונה ממוזערת מ-URL"""
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            return filename
    except Exception as e:
        print(f"שגיאה בהורדת תמונה ממוזערת: {str(e)}")
    return None


class ProgressCallback:
    def __init__(self, client, chat_id, message_id):
        self.client = client
        self.chat_id = chat_id
        self.message_id = message_id
        self.last_percentage = -1

    def __call__(self, d):
        if d['status'] == 'downloading':
            try:
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)

                if total_bytes:
                    percentage = int((downloaded_bytes / total_bytes) * 100)

                    # עדכון כל 5 אחוזים ורק אם השתנה
                    if percentage % 5 == 0 and percentage != self.last_percentage:
                        self.last_percentage = percentage
                        try:
                            self.client.edit_message_text(
                                chat_id=self.chat_id,
                                message_id=self.message_id,
                                text=f"*⏳ מוריד את הקובץ...*\nהתקדמות: {percentage}%",
                                parse_mode='markdown'
                            )
                        except Exception as e:
                            if "Message is not modified" not in str(e):
                                raise e
            except Exception as e:
                print(f"שגיאה בעדכון התקדמות: {str(e)}")



def create_ydl_opts(format_type='video', format_id=None, progress_callback=None):
    """יוצר אפשרויות yt-dlp עם קוקיז"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'progress_hooks': [progress_callback] if progress_callback else None,
        'writethumbnail': True,  # שמירת תמונה ממוזערת
        'postprocessors': [{
            'key': 'FFmpegThumbnailsConvertor',
            'format': 'jpg'
        }]
    }

    if format_type == 'audio' and format_id:
        ydl_opts['format'] = format_id
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        })
    elif format_id:
        ydl_opts.update({
            'format': f'{format_id}+bestaudio',
            'merge_output_format': 'mp4',
        })
    elif format_type == 'audio':
        ydl_opts.update({'format': 'bestaudio/best'})
    else:
        ydl_opts.update({
            'format': 'bestvideo+bestaudio',
            'merge_output_format': 'mp4'
        })

    return ydl_opts



def check_storage_channel(client, video_url, format_type):
    """בודק אם הקובץ כבר קיים בערוץ האחסון"""
    try:
        messages = client.get_discussion_history(STORAGE_CHANNEL_ID, limit=100)
        for message in messages:
            if message.caption and video_url in message.caption:
                if format_type == 'audio' and message.audio:
                    return message.audio.file_id
                elif format_type == 'video' and message.video:
                    return message.video.file_id
    except Exception as e:
        print(f"שגיאה בבדיקת ערוץ האחסון: {e}")
        pass
    return None



def cleanup_files(*files):
    """מנקה קבצים זמניים"""
    for file in files:
        if file and os.path.exists(file):
            try:
                os.remove(file)
            except Exception as e:
                print(f"שגיאה במחיקת קובץ {file}: {str(e)}")



@app.on_message(filters.command(['start']))
def send_welcome(client, message):
    welcome_text = """
*ברוכים הבאים לבוט ההורדות מיוטיוב!* 🎉

*איך להשתמש:*
1. שלח קישור ליוטיוב 🔗
2. בחר אם ברצונך להוריד כאודיו 🎵 או וידאו 🎬
3. בחר את האיכות הרצויה ⚙️
4. המתן להורדה ושליחת הקובץ ⏳

*תכונות:*
• תמיכה בהורדת אודיו (MP3) 🎵
• תמיכה בהורדת וידאו (MP4) 🎬
• בחירת איכות גבוהה ⚡
• תמונות ממוזערות מהשיר ביוטיוב אוטומטיות 🖼️

*הבוט תומך בכל הסרטונים מיוטיוב! 🚀*
    """
    client.send_message(message.chat.id, welcome_text, parse_mode='markdown')



@app.on_message(filters.text)
def check_youtube_link(client, message):
    try:
        if "youtube.com" in message.text or "youtu.be" in message.text:
            video_info_dict[message.chat.id] = {'url': message.text}

            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🎵 אודיו", callback_data="audio"),
                        InlineKeyboardButton("🎬 וידאו", callback_data="video")
                    ]
                ]
            )

            client.send_message(message.chat.id, "*בחר את סוג הקובץ להורדה:*", reply_markup=markup, parse_mode='markdown')
        else:
            client.send_message(message.chat.id, "*❌ אנא שלח קישור תקין ליוטיוב*", parse_mode='markdown')

    except Exception as e:
        error_msg = str(e)[:50]
        client.send_message(message.chat.id, f"*❌ שגיאה:* {error_msg}", parse_mode='markdown')



@app.on_callback_query(filters.regex(r"^(audio|video)$"))
def handle_type_choice(client: Client, callback_query: CallbackQuery):
    try:
        chat_id = callback_query.message.chat.id
        message_id = callback_query.message.id

        if chat_id not in video_info_dict:
            callback_query.answer("❌ שגיאה: אנא שלח קישור חדש")
            return

        video_url = video_info_dict[chat_id]['url']

        client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="*🔍 מאחזר מידע על הקובץ...*",
            parse_mode='markdown'
        )

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None
        }

        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                formats = info['formats']

                markup = InlineKeyboardMarkup([])
                
                if callback_query.data == "audio":
                    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                    if not audio_formats:
                        raise Exception("לא נמצאו פורמטים של אודיו")

                    for fmt in sorted(audio_formats, key=lambda x: x.get('abr', 0), reverse=True)[:5]:
                        quality = fmt.get('abr', 'N/A')
                        format_id = fmt['format_id']
                        size = fmt.get('filesize', 0) // (1024 * 1024)  # MB
                        btn_text = f"🎵 {quality}k ({size}MB)"
                        markup.inline_keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"a_{format_id}")])
                else:
                    video_formats = []
                    seen_qualities = set()

                    for fmt in formats:
                        if (fmt.get('vcodec', 'none') != 'none' and
                                fmt.get('height', 0) >= 360 and
                                fmt.get('height', 0) not in seen_qualities):
                            video_formats.append(fmt)
                            seen_qualities.add(fmt.get('height', 0))

                    if not video_formats:
                        raise Exception("לא נמצאו פורמטים של וידאו")

                    video_formats.sort(key=lambda x: (x.get('height', 0), x.get('tbr', 0)), reverse=True)

                    for fmt in video_formats[:5]:
                        quality = fmt.get('height', 'N/A')
                        format_id = fmt['format_id']
                        size = fmt.get('filesize', 0) // (1024 * 1024)  # MB
                        btn_text = f"🎬 {quality}p ({size}MB)"
                        markup.inline_keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"v_{format_id}")])

                video_info_dict[chat_id]['info'] = info
                safe_title = escape_markdown(info.get('title', 'סרטון ללא כותרת'))

                client.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"*{safe_title}*\n\n*בחר את האיכות הרצויה:*",
                    reply_markup=markup,
                    parse_mode='markdown'
                )

            except Exception as e:
                error_message = f"*❌ שגיאה בקבלת מידע על הקובץ:*\n{escape_markdown(str(e))}"
                client.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    parse_mode='markdown'
                )
                if chat_id in video_info_dict:
                    del video_info_dict[chat_id]

    except Exception as e:
        error_msg = escape_markdown(str(e)[:200])
        try:
            client.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.id,
                text=f"*❌ שגיאה:*\n{error_msg}",
                parse_mode='markdown'
            )
        except:
            callback_query.answer("❌ אירעה שגיאה")

        if chat_id in video_info_dict:
            del video_info_dict[chat_id]



@app.on_callback_query(filters.regex(r"^(a_|v_)"))
def handle_quality_choice(client: Client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    media_type, format_id = callback_query.data.split('_')
    video_url = video_info_dict[chat_id]['url']
    filename = None
    thumb_path = None

    try:
        # בדיקה אם הקובץ כבר קיים בערוץ האחסון
        existing_file_id = check_storage_channel(client, video_url, 'audio' if media_type == 'a' else 'video')
        if existing_file_id:
            if media_type == 'a':
                info = video_info_dict[chat_id]['info']
                safe_title = escape_markdown(info.get('title', ''))
                caption = f"*{safe_title}*\n\nאיכות: *{info.get('abr', 'N/A')}k*\n\nהועלה ע\"י @the_my_first_robot"
                client.send_audio(
                    chat_id=chat_id,
                    audio=existing_file_id,
                    caption=caption,
                    parse_mode='markdown',
                    title=info.get('title'),
                    duration=info.get('duration')
                )
            else:
                info = video_info_dict[chat_id]['info']
                safe_title = escape_markdown(info.get('title', ''))
                caption = f"*{safe_title}*\n\nאיכות: *{info.get('height', 'N/A')}p*\n\nהועלה ע\"י @the_my_first_robot"
                client.send_video(
                    chat_id=chat_id,
                    video=existing_file_id,
                    caption=caption,
                    parse_mode='markdown',
                    duration=info.get('duration'),
                    width=info.get('width', 0),
                    height=info.get('height', 0),
                    supports_streaming=True
                )
            return

        # שליחת הודעת התחלת הורדה
        progress_message = client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="*⏳ מוריד את הקובץ...*\nהתקדמות: 0%",
            parse_mode='markdown'
        )

        # יצירת callback להתקדמות
        progress_callback = ProgressCallback(client, chat_id, progress_message.id)

        # הגדרות ההורדה
        ydl_opts = create_ydl_opts(
            'audio' if media_type == 'a' else 'video',
            format_id,
            progress_callback
        )
        ydl_opts['outtmpl'] = '%(title)s.%(ext)s'

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            filename = ydl.prepare_filename(info)
            safe_title = escape_markdown(info.get('title', ''))

            filesize = info.get('filesize', 0) // (1024 * 1024)  # MB
            if filesize > 50:
                client.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_message.id,
                    text="*❌ לא ניתן להוריד קבצים מעל 50MB בגלל מגבלות טלגרם.*",
                    parse_mode='markdown'
                )
                return

            if media_type == 'a':
                mp3_filename = os.path.splitext(filename)[0] + '.mp3'
                filename = mp3_filename

                with open(mp3_filename, 'rb') as audio:
                    # העלאה לערוץ האחסון עם אותו פורמט
                    caption = f"*{safe_title}*\n\nאיכות: *{info.get('abr', 'N/A')}k*\n\nהועלה ע\"י @the_my_first_robot"
                    stored_message = client.send_audio(
                        chat_id=STORAGE_CHANNEL_ID,
                        audio=audio,
                        caption=caption,
                        parse_mode='markdown',
                        title=info.get('title'),
                        duration=info.get('duration')
                    )

                    # שליחה למשתמש מהערוץ
                    client.send_audio(
                        chat_id=chat_id,
                        audio=stored_message.audio.file_id,
                        caption=caption,
                        parse_mode='markdown',
                        title=info.get('title'),
                        duration=info.get('duration')
                    )

            else:  # וידאו
                if os.path.exists(filename):
                    # נסה למצוא את התמונה הממוזערת שנשמרה
                    thumb_path = os.path.splitext(filename)[0] + '.jpg'

                    # אם אין תמונה ממוזערת, נסה להוריד מהקישור
                    if not os.path.exists(thumb_path) and info.get('thumbnail'):
                        thumb_path = download_thumbnail(info['thumbnail'], thumb_path)

                    thumb_data = None
                    if thumb_path and os.path.exists(thumb_path):
                        with open(thumb_path, 'rb') as thumb_file:
                            thumb_data = thumb_file.read()

                    with open(filename, 'rb') as video:
                        # העלאה לערוץ האחסון עם אותו פורמט
                        caption = f"*{safe_title}*\n\nאיכות: *{info.get('height', 'N/A')}p*\n\nהועלה ע\"י @the_my_first_robot"
                        stored_message = client.send_video(
                            chat_id=STORAGE_CHANNEL_ID,
                            video=video,
                            caption=caption,
                            parse_mode='markdown',
                            thumb=thumb_data,
                            duration=info.get('duration'),
                            width=info.get('width', 0),
                            height=info.get('height', 0),
                            supports_streaming=True
                        )

                        # שליחה למשתמש מהערוץ
                        client.send_video(
                            chat_id=chat_id,
                            video=stored_message.video.file_id,
                            caption=caption,
                            parse_mode='markdown',
                            duration=info.get('duration'),
                            width=info.get('width', 0),
                            height=info.get('height', 0),
                            supports_streaming=True
                        )

        # ניקוי
        try:
            client.delete_messages(chat_id, progress_message.id)
        except:
            pass
        cleanup_files(filename, thumb_path)
        del video_info_dict[chat_id]

    except Exception as e:
        error_msg = escape_markdown(str(e)[:200])
        try:
            client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"*❌ שגיאה בהורדה:*\n{error_msg}",
                parse_mode='markdown'
            )
        except:
            callback_query.answer("❌ אירעה שגיאה")

        # ניקוי במקרה של שגיאה
        cleanup_files(filename, thumb_path)
        if chat_id in video_info_dict:
            del video_info_dict[chat_id]

# פונקציה של Flask כדי לקבל עדכונים מהטלגרם
@flask_app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        # הדפסת הלוג
        print(f"קיבל עדכון: {update}")
        if update.message:
          app.process_new_messages([update.message])
        elif update.callback_query:
          app.process_callback_query(update.callback_query)
        return 'OK', 200
    else:
        return 'OK', 200

# נקודת כניסה של Flask
if __name__ == "__main__":
    # הפעלת השרת של Flask בפורט 8000
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

