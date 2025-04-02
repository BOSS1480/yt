FROM python:3.10-slim

# עדכון רשימת החבילות והתקנת gcc וכלי פיתוח
RUN apt-get update && apt-get install -y gcc build-essential

# הגדרת תיקיית עבודה
WORKDIR /app

# העתקת הקבצים הדרושים
COPY main.py /app/main.py
COPY requirements.txt /app/requirements.txt
COPY cookies.txt /app/cookies.txt

# עדכון pip והתקנת התלויות
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# חשיפת הפורט 8000 (ל-Koyeb)
EXPOSE 8000

# הפעלת הבוט
CMD ["python", "main.py"]
