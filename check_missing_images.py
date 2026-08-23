# check_missing_images.py
from app import app
from models import db, Word

with app.app_context():
    total = Word.query.count()
    with_images = Word.query.filter(Word.image_url.isnot(None)).count()
    without_images = total - with_images

    print(f"📊 Всего слов: {total}")
    print(f"✅ С изображениями: {with_images}")
    print(f"❌ Без изображений: {without_images}")

    if without_images > 0:
        print("\n❌ Первые 10 слов без изображений:")
        for word in Word.query.filter(Word.image_url.is_(None)).limit(10).all():
            print(f"  - {word.word}")