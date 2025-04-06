# השתמש בתמונה בסיסית של Python
FROM python:3.11-slim-buster

# הגדר את סביבת העבודה בתוך הדוקר
WORKDIR /app

# העתק את קובץ הדרישות
COPY requirements.txt /app

# התקן את התלות
RUN pip install --no-cache-dir -r requirements.txt

# העתק את שאר קוד האפליקציה
COPY . /app

# חשוף את הפורט עליו האפליקציה יאזין
EXPOSE 8000

# הפעל את הבוט
CMD ["python", "bot.py"]

