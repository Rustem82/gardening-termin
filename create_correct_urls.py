# create_correct_urls.py
import os
import re

# ВАШ STORE ID (из Environment Variables)
STORE_ID = "store_W6SAmavz4a8tGG7Q"


def create_correct_urls():
    upload_folder = 'static/uploads'
    if not os.path.exists(upload_folder):
        print(f"❌ Папка {upload_folder} не найдена!")
        return

    images = [f for f in os.listdir(upload_folder)
              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]

    print(f"📸 Найдено {len(images)} изображений")

    # Проверяем, существует ли файл со старыми ссылками
    old_urls = {}
    try:
        with open('blob_urls.txt', 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    old_urls[key.strip().lower()] = value.strip()
        print(f"📝 Загружено {len(old_urls)} старых ссылок")
    except:
        print("📝 Старых ссылок нет, создаем новые")

    # Создаем правильные ссылки
    with open('blob_urls_correct.txt', 'w', encoding='utf-8') as f:
        for filename in images:
            key = os.path.splitext(filename)[0]
            key = key.replace('-', ' ').replace('_', ' ')
            key = re.sub(r'\s+\d+$', '', key)

            # Правильный URL
            url = f"https://{STORE_ID}.blob.vercel-storage.com/{filename}"
            f.write(f"{key} = {url}\n")
            print(f"✅ {key} -> {url}")

    print(f"\n✅ Создано {len(images)} правильных ссылок")
    print("📝 Ссылки сохранены в blob_urls_correct.txt")


if __name__ == '__main__':
    create_correct_urls()