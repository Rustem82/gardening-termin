# update_blob_urls.py
from app import app
from models import db, Word
import re


def update_blob_urls():
    with app.app_context():
        # Загружаем ссылки из файла
        blob_urls = {}
        try:
            with open('blob_urls.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        blob_urls[key.strip().lower()] = value.strip()
        except FileNotFoundError:
            print("❌ Файл blob_urls.txt не найден!")
            return

        print(f"📸 Загружено {len(blob_urls)} ссылок из файла")

        updated = 0
        for word in Word.query.all():
            word_key = word.word.lower().strip()
            # Убираем апострофы и специальные символы
            word_key = re.sub(r'[‘\'`]', '', word_key)
            word_key = word_key.replace(' ', '_').replace('—', '_')
            word_key = re.sub(r'[^a-zA-Z0-9_]', '', word_key)

            if word_key in blob_urls:
                word.image_url = blob_urls[word_key]
                updated += 1
                print(f"✅ {word.word} обновлен")

        if updated > 0:
            db.session.commit()
            print(f"\n✅ Обновлено {updated} записей")
        else:
            print("\n❌ Ничего не обновлено")


if __name__ == '__main__':
    update_blob_urls()