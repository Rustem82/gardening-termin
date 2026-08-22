# fix_and_check.py
from app import app
from models import db, Word
import os
import re


def check_and_fix():
    with app.app_context():
        print("=" * 60)
        print("🔍 ПРОВЕРКА СТАТУСА ИЗОБРАЖЕНИЙ")
        print("=" * 60)

        # 1. Проверяем папку uploads
        upload_folder = 'static/uploads'
        if os.path.exists(upload_folder):
            files = os.listdir(upload_folder)
            print(f"\n📁 Папка {upload_folder}:")
            print(f"   Всего файлов: {len(files)}")
            print(f"   Первые 5 файлов: {files[:5]}")
        else:
            print(f"\n❌ Папка {upload_folder} НЕ СУЩЕСТВУЕТ!")
            return

        # 2. Проверяем слова в базе данных
        total_words = Word.query.count()
        words_with_images = Word.query.filter(Word.image_url.isnot(None)).count()
        words_without_images = Word.query.filter(Word.image_url.is_(None)).count()

        print(f"\n📊 СТАТИСТИКА БАЗЫ ДАННЫХ:")
        print(f"   Всего слов: {total_words}")
        print(f"   С изображениями: {words_with_images}")
        print(f"   Без изображений: {words_without_images}")

        # 3. Проверяем, есть ли слова с изображениями, у которых файл отсутствует
        if words_with_images > 0:
            print("\n🔍 ПРОВЕРКА СУЩЕСТВУЮЩИХ СВЯЗЕЙ:")
            broken_links = 0
            for word in Word.query.filter(Word.image_url.isnot(None)).limit(20).all():
                filepath = word.image_url.lstrip('/')
                if os.path.exists(filepath):
                    print(f"   ✅ {word.word} -> файл существует")
                else:
                    print(f"   ❌ {word.word} -> файл ОТСУТСТВУЕТ: {filepath}")
                    broken_links += 1

            if broken_links > 0:
                print(f"\n⚠️ Найдено {broken_links} битых ссылок")

        # 4. Пытаемся привязать изображения к словам без изображений
        if words_without_images > 0:
            print(f"\n📸 ПРИВЯЗКА ИЗОБРАЖЕНИЙ К {words_without_images} СЛОВАМ")

            # Создаем словарь изображений
            image_files = {}
            for f in files:
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                    name = os.path.splitext(f)[0]
                    name = re.sub(r'[_\-]\d+$', '', name)
                    name = re.sub(r'[_\-]v\d+$', '', name)
                    name = name.replace('_', ' ').replace('-', ' ').lower().strip()
                    if name not in image_files:
                        image_files[name] = []
                    image_files[name].append(f)

            print(f"   Найдено {len(image_files)} уникальных имен изображений")

            linked = 0
            for word in Word.query.filter(Word.image_url.is_(None)).all():
                word_key = word.word.lower().strip()

                # Ищем точное совпадение
                if word_key in image_files:
                    word.image_url = f"/{upload_folder}/{image_files[word_key][0]}"
                    linked += 1
                    print(f"   ✅ {word.word} -> {image_files[word_key][0]}")
                    continue

                # Ищем частичное совпадение
                found = False
                for img_name, files_list in image_files.items():
                    if word_key in img_name or img_name in word_key:
                        word.image_url = f"/{upload_folder}/{files_list[0]}"
                        linked += 1
                        found = True
                        print(f"   ✅ {word.word} -> {files_list[0]} (частичное)")
                        break

            if linked > 0:
                db.session.commit()
                print(f"\n✅ Привязано {linked} изображений")
            else:
                print(f"\n❌ Новых привязок не найдено")

        # 5. Финальная статистика
        print("\n" + "=" * 60)
        print("📊 ИТОГОВАЯ СТАТИСТИКА:")
        print("=" * 60)

        with_images = Word.query.filter(Word.image_url.isnot(None)).count()
        without_images = Word.query.filter(Word.image_url.is_(None)).count()

        print(f"   Всего слов: {Word.query.count()}")
        print(f"   С изображениями: {with_images}")
        print(f"   Без изображений: {without_images}")

        # Показываем примеры
        if with_images > 0:
            print("\n📸 ПРИМЕРЫ СЛОВ С ИЗОБРАЖЕНИЯМИ:")
            for word in Word.query.filter(Word.image_url.isnot(None)).limit(5).all():
                print(f"   {word.word} -> {word.image_url}")

        if without_images > 0:
            print("\n❌ ПРИМЕРЫ СЛОВ БЕЗ ИЗОБРАЖЕНИЙ:")
            for word in Word.query.filter(Word.image_url.is_(None)).limit(5).all():
                print(f"   {word.word}")


if __name__ == '__main__':
    check_and_fix()