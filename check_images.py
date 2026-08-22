# check_images.py
from app import app
from models import db, Word
import os
import re

with app.app_context():
    upload_folder = 'static/uploads'

    if not os.path.exists(upload_folder):
        print(f"❌ Папка {upload_folder} не найдена!")
        exit()

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

    # Показываем первые 10 изображений для проверки
    print("\n🔍 Первые 10 изображений:")
    for filename, name in images[:10]:
        print(f"  {filename} -> {name}")

    # Проверяем, есть ли слова, соответствующие именам файлов
    print("\n🔍 Проверка соответствия:")
    found = 0
    not_found = []

    for filename, image_name in images[:20]:  # Проверяем первые 20
        # Ищем точное совпадение
        word = Word.query.filter(Word.word.ilike(image_name)).first()

        if not word:
            # Ищем частичное совпадение
            word = Word.query.filter(Word.word.ilike(f'%{image_name}%')).first()

        if word:
            found += 1
            print(f"  ✅ {filename} -> {word.word}")
        else:
            not_found.append(filename)
            print(f"  ❌ {filename} -> не найдено")

    print(f"\n📊 Результат:")
    print(f"  Найдено соответствий: {found}")
    print(f"  Не найдено: {len(not_found)}")

    if not_found:
        print(f"\n❌ Примеры файлов без соответствия:")
        for f in not_found[:5]:
            print(f"  {f}")