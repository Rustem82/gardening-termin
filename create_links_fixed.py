# create_links_fixed.py
import os
import re

# ВАШ STORE ID (скопируйте из Environment Variables в Vercel)
STORE_ID = "store_W6SAmavz4a8tGG7Q"


def create_links():
    if not STORE_ID or STORE_ID == "ваш_BLOB_STORE_ID":
        print("❌ Store ID не найден!")
        print("1. Перейдите в Environment Variables в Vercel")
        print("2. Нажмите на BLOB_STORE_ID")
        print("3. Скопируйте значение")
        print("4. Вставьте его в переменную STORE_ID в этом файле")
        return

    upload_folder = 'static/uploads'
    if not os.path.exists(upload_folder):
        print(f"❌ Папка {upload_folder} не найдена!")
        return

    images = [f for f in os.listdir(upload_folder)
              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]

    print(f"📸 Найдено {len(images)} изображений")

    with open('blob_urls.txt', 'w', encoding='utf-8') as f:
        for filename in images:
            key = os.path.splitext(filename)[0]
            key = key.replace('-', ' ').replace('_', ' ')
            key = re.sub(r'\s+\d+$', '', key)
            url = f"https://{STORE_ID}.blob.vercel-storage.com/{filename}"
            f.write(f"{key} = {url}\n")
            print(f"✅ {key} -> {url}")

    print(f"\n✅ Создано {len(images)} ссылок")
    print("📝 Ссылки сохранены в blob_urls.txt")


if __name__ == '__main__':
    create_links()