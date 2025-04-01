FROM python:3.9-slim

WORKDIR /app

# העתקת קובץ הדרישות והתקנתן
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# העתקת קבצי הפרויקט
COPY . .

# חשיפת פורט 8000
EXPOSE 8000

# הפעלת הקובץ הראשי
CMD ["python", "bot.py"]
