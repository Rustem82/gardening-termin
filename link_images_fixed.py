# link_images_fixed.py
from app import app
from models import db, Word
import os
import re


def link_images():
    with app.app_context():
        upload_folder = 'static/uploads'

        if not os.path.exists(upload_folder):
            print(f"❌ Папка {upload_folder} не найдена!")
            return

        # Получаем все изображения
        images = []
        for f in os.listdir(upload_folder):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                # Убираем расширение и суффиксы
                name = os.path.splitext(f)[0]
                name = re.sub(r'[_\-]\d+$', '', name)
                name = re.sub(r'[_\-]v\d+$', '', name)
                name = name.replace('_', ' ').replace('-', ' ').lower().strip()
                images.append((f, name))

        print(f"📸 Найдено {len(images)} изображений")

        linked = 0
        already_linked = 0
        not_found = []

        for filename, image_name in images:
            # Ищем точное совпадение
            word = Word.query.filter(Word.word.ilike(image_name)).first()

            if not word:
                # Ищем частичное совпадение (начинается с)
                word = Word.query.filter(Word.word.ilike(f'{image_name}%')).first()

            if not word:
                # Ищем частичное совпадение (содержит)
                word = Word.query.filter(Word.word.ilike(f'%{image_name}%')).first()

            if word:
                if not word.image_url:
                    word.image_url = f"/{upload_folder}/{filename}"
                    linked += 1
                    print(f"  ✅ {word.word} <- {filename}")
                else:
                    already_linked += 1
                    # print(f"  ⏭️ {word.word} уже имеет изображение")
            else:
                not_found.append(filename)
                # print(f"  ❌ {filename} -> не найдено")

        if linked > 0:
            db.session.commit()
            print(f"\n✅ Привязано {linked} изображений")
        else:
            print("\n❌ Новых привязок не найдено")

        print(f"⏭️ Уже были привязаны: {already_linked}")
        print(f"❌ Не найдено соответствий: {len(not_found)}")

        # Показываем статистику
        total_words = Word.query.count()
        words_with_images = Word.query.filter(Word.image_url.isnot(None)).count()
        print(f"\n📊 Статистика:")
        print(f"  Всего слов: {total_words}")
        print(f"  С изображениями: {words_with_images}")

        # Показываем примеры слов с изображениями
        if words_with_images > 0:
            print("\n📸 Примеры слов с изображениями:")
            for word in Word.query.filter(Word.image_url.isnot(None)).limit(5).all():
                print(f"  {word.word} -> {word.image_url}")


if __name__ == '__main__':
    link_images()