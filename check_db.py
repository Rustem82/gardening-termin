# check_db.py
from app import app
from models import db, Word

with app.app_context():
    total = Word.query.count()
    print(f"Всего слов в базе данных: {total}")

    if total > 0:
        # Покажем первые 10 слов
        words = Word.query.limit(10).all()
        print("\nПервые 10 слов в базе:")
        for word in words:
            print(f"  - {word.word}")
    else:
        print("\n❌ База данных ПУСТА! Нужно импортировать данные.")