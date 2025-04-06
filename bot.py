import telebot
from yt_dlp import YoutubeDL
import os
import subprocess
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request  # ייבוא Flask

# הגדרות בסיסיות
# BOT_TOKEN = 'YOUR_BOT_TOKEN' #החלף את הטוקן שלך
COOKIES_FILE = 'cookies.txt'
STORAGE_CHANNEL_ID = '-1002402574884'

# הפעלת Flask
app = Flask(__name__)
bot = telebot.TeleBot(os.environ.get('BOT_TOKEN')) # קריאה לטוקן מהסביבה

video_info_dict = {}

def escape_markdown(text):
    """מנקה תווים מיוחדים מהטקסט למניעת שגיאות בפרסור markdown"""
    if not text:
        return ""
    # מחליף מקף עם רווח במקף רגיל
    text = text.replace(' - ', ' - ')
    # מטפל בתווים מיוחדים
    special_chars = ['_', '"']
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
    def __init__(self, chat_id, message_id):
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
                            bot.edit_message_text(
                                f"*⏳ מוריד את הקובץ...*\nהתקדמות: {percentage}%",
                                chat_id=self.chat_id,
                                message_id=self.message_id,
                                parse_mode='Markdown'
                            )
                        except telebot.apihelper.ApiTelegramException as e:
                            if "message is not modified" not in str(e):
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

def check_storage_channel(video_url, format_type):
    """בודק אם הקובץ כבר קיים בערוץ האחסון"""
    try:
        messages = bot.get_chat_history(STORAGE_CHANNEL_ID, limit=100)
        for message in messages:
            if message.caption and video_url in message.caption:
                if format_type == 'audio' and message.audio:
                    return message.audio.file_id
                elif format_type == 'video' and message.video:
                    return message.video.file_id
    except Exception:
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

@bot.message_handler(commands=['start'])
def send_welcome(message):
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
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def check_youtube_link(message):
    try:
        if "youtube.com" in message.text or "youtu.be" in message.text:
            video_info_dict[message.chat.id] = {'url': message.text}
            
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("🎵 אודיו", callback_data="audio"),
                InlineKeyboardButton("🎬 וידאו", callback_data="video")
            )
            
            bot.reply_to(message, "*בחר את סוג הקובץ להורדה:*", reply_markup=markup, parse_mode='Markdown')
        else:
            bot.reply_to(message, "*❌ אנא שלח קישור תקין ליוטיוב*", parse_mode='Markdown')
            
    except Exception as e:
        error_msg = str(e)[:50]
        bot.reply_to(message, f"*❌ שגיאה:* {error_msg}", parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data in ["audio", "video"])
def handle_type_choice(call):
    try:
        chat_id = call.message.chat.id
        if chat_id not in video_info_dict:
            bot.answer_callback_query(call.id, "❌ שגיאה: אנא שלח קישור חדש")
            return
            
        video_url = video_info_dict[chat_id]['url']
        
        status_message = bot.edit_message_text(
            "*🔍 מאחזר מידע על הקובץ...*",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode='Markdown'
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
                
                markup = InlineKeyboardMarkup()
                
                if call.data == "audio":
                    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                    if not audio_formats:
                        raise Exception("לא נמצאו פורמטים של אודיו")
                        
                    for fmt in sorted(audio_formats, key=lambda x: x.get('abr', 0), reverse=True)[:5]:
                        quality = fmt.get('abr', 'N/A')
                        format_id = fmt['format_id']
                        size = fmt.get('filesize', 0) // (1024 * 1024)  # MB
                        btn_text = f"🎵 {quality}k ({size}MB)"
                        markup.row(InlineKeyboardButton(btn_text, callback_data=f"a_{format_id}"))
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
                        markup.row(InlineKeyboardButton(btn_text, callback_data=f"v_{format_id}"))
                
                video_info_dict[chat_id]['info'] = info
                safe_title = escape_markdown(info.get('title', 'סרטון ללא כותרת'))
                
                bot.edit_message_text(
                    f"*{safe_title}*\n\n*בחר את האיכות הרצויה:*",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                error_message = f"*❌ שגיאה בקבלת מידע על הקובץ:*\n{escape_markdown(str(e))}"
                bot.edit_message_text(
                    error_message,
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    parse_mode='Markdown'
                )
                if chat_id in video_info_dict:
                    del video_info_dict[chat_id]
                    
    except Exception as e:
        error_msg = escape_markdown(str(e)[:200])
        try:
            bot.edit_message_text(
                f"*❌ שגיאה:*\n{error_msg}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='Markdown'
            )
        except:
            bot.answer_callback_query(call.id, "❌ אירעה שגיאה")
        
        if chat_id in video_info_dict:
            del video_info_dict[chat_id]

@bot.callback_query_handler(func=lambda call: call.data.startswith(('a_', 'v_')))
def handle_quality_choice(call):
    chat_id = call.message.chat.id
    media_type, format_id = call.data.split('_')
    video_url = video_info_dict[chat_id]['url']
    filename = None
    thumb_path = None
    
    try:
        # בדיקה אם הקובץ כבר קיים בערוץ האחסון
        existing_file_id = check_storage_channel(video_url, 'audio' if media_type == 'a' else 'video')
        if existing_file_id:
            if media_type == 'a':
                info = video_info_dict[chat_id]['info']
                safe_title = escape_markdown(info.get('title', ''))
                caption = f"*{safe_title}*\n\nאיכות: *{info.get('abr', 'N/A')}k*\n\nהועלה ע\"י @the\_my\_first\_robot"
                bot.send_audio(
                    chat_id,
                    existing_file_id,
                    caption=caption,
                    parse_mode='Markdown',
                    title=info.get('title'),
                    duration=info.get('duration')
                )
            else:
                info = video_info_dict[chat_id]['info']
                safe_title = escape_markdown(info.get('title', ''))
                caption = f"*{safe_title}*\n\nאיכות: *{info.get('height', 'N/A')}p*\n\nהועלה ע\"י @the\_my\_first\_robot"
                bot.send_video(
                    chat_id,
                    existing_file_id,
                    caption=caption,
                    parse_mode='Markdown',
                    duration=info.get('duration'),
                    width=info.get('width', 0),
                    height=info.get('height', 0),
                    supports_streaming=True
                )
            return

        # שליחת הודעת התחלת הורדה
        progress_message = bot.edit_message_text(
            "*⏳ מוריד את הקובץ...*\nהתקדמות: 0%",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode='Markdown'
        )

        # יצירת callback להתקדמות
        progress_callback = ProgressCallback(chat_id, progress_message.message_id)
        
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
                bot.edit_message_text(
                    "*❌ לא ניתן להוריד קבצים מעל 50MB בגלל מגבלות טלגרם.*",
                    chat_id=chat_id,
                    message_id=progress_message.message_id,
                    parse_mode='Markdown'
                )
                return

            if media_type == 'a':
                mp3_filename = os.path.splitext(filename)[0] + '.mp3'
                filename = mp3_filename

                with open(mp3_filename, 'rb') as audio:
                    # העלאה לערוץ האחסון עם אותו פורמט
                    caption = f"*{safe_title}*\n\nאיכות: *{info.get('abr', 'N/A')}k*\n\nהועלה ע\"י @the\_my\_first\_robot"
                    stored_message = bot.send_audio(
                        STORAGE_CHANNEL_ID,
                        audio,
                        caption=caption,
                        parse_mode='Markdown',
                        title=info.get('title'),
                        duration=info.get('duration')
                    )

                    # שליחה למשתמש מהערוץ
                    bot.send_audio(
                        chat_id,
                        stored_message.audio.file_id,
                        caption=caption,
                        parse_mode='Markdown',
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
                        caption = f"*{safe_title}*\n\nאיכות: *{info.get('height', 'N/A')}p*\n\nהועלה ע\"י @the\_my\_first\_robot"
                        stored_message = bot.send_video(
                            STORAGE_CHANNEL_ID,
                            video,
                            caption=caption,
                            parse_mode='Markdown',
                            thumb=thumb_data,
                            duration=info.get('duration'),
                            width=info.get('width', 0),
                            height=info.get('height', 0),
                            supports_streaming=True
                        )

                        # שליחה למשתמש מהערוץ
                        bot.send_video(
                            chat_id,
                            stored_message.video.file_id,
                            caption=caption,
                            parse_mode='Markdown',
                            duration=info.get('duration'),
                            width=info.get('width', 0),
                            height=info.get('height', 0),
                            supports_streaming=True
                        )

        # ניקוי
        try:
            bot.delete_message(chat_id, progress_message.message_id)
        except:
            pass
        cleanup_files(filename, thumb_path)
        del video_info_dict[chat_id]

    except Exception as e:
        error_msg = escape_markdown(str(e)[:200])
        try:
            bot.edit_message_text(
                f"*❌ שגיאה בהורדה:*\n{error_msg}",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode='Markdown'
            )
        except:
            bot.answer_callback_query(call.id, "❌ אירעה שגיאה")
        
        # ניקוי במקרה של שגיאה
        cleanup_files(filename, thumb_path)
        if chat_id in video_info_dict:
            del video_info_dict[chat_id]

# פונקציה של Flask כדי לקבל עדכונים מהטלגרם
@app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'OK', 200

# נקודת כניסה של Flask
if __name__ == "__main__":
    # הפעלת השרת של Flask בפורט 8000
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
