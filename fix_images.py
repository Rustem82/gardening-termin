# fix_images.py
from app import app
from models import db, Word
import os
import re


def fix_image_urls():
    """Исправляет и привязывает все изображения"""
    upload_folder = 'static/uploads'

    if not os.path.exists(upload_folder):
        print(f"Папка {upload_folder} не найдена!")
        return

    # Получаем все изображения
    images = []
    for f in os.listdir(upload_folder):
        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            # Убираем расширение и суффиксы
            name = re.sub(r'[_\-]\d+$', '', os.path.splitext(f)[0])
            name = re.sub(r'[_\-]v\d+$', '', name)
            name = name.replace('_', ' ').lower().strip()
            images.append((f, name))

    print(f"Найдено {len(images)} изображений")

    with app.app_context():
        fixed = 0
        for filename, word_name in images:
            # Ищем слово
            word = Word.query.filter(
                Word.word.ilike(f'%{word_name}%')
            ).first()

            if word:
                # Обновляем URL
                new_url = f"/{upload_folder}/{filename}"
                if word.image_url != new_url:
                    word.image_url = new_url
                    fixed += 1
                    print(f"✅ Привязано: {word.word} -> {filename}")

        if fixed > 0:
            db.session.commit()
            print(f"\n✅ Всего исправлено: {fixed} записей")
        else:
            print("\n❌ Новых привязок не найдено")


if __name__ == '__main__':
    fix_image_urls()