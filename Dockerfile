# השתמשו בגרסת Python 3.10-slim
FROM python:3.10-slim

# מגדירים משתנה סביבה כדי למנוע יצירת cache על ידי Pyrogram
ENV PYROGRAM_NO_CACHE=1

# הגדרת תיקיית עבודה
WORKDIR /app

# העתקת קבצי הקוד, הדרישות, cookies.txt
COPY main.py /app/main.py
COPY requirements.txt /app/requirements.txt
COPY cookies.txt /app/cookies.txt

# התקנת התלויות
RUN pip install --no-cache-dir -r requirements.txt

# חשיפת הפורט 8000 (ל-Koyeb)
EXPOSE 8000

# הפעלת הבוט
CMD ["python", "bot.py"]
