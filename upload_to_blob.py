# upload_to_blob.py
import os
import re
import requests
import json

# Токен для Vercel Blob - замените на ваш!
TOKEN = "vercel_blob_rw_W6SAmavz4a8tGG7Q_kz6pt9SHHd3MrKK684ZghRp9qkcYQT"


def upload_images():
    if not TOKEN or TOKEN == "ваш_токен_из_vercel":
        print("❌ BLOB_READ_WRITE_TOKEN не настроен!")
        print("1. Зайдите в Vercel → ваш проект")
        print("2. Нажмите Storage → Create Database → Blob")
        print("3. Скопируйте токен")
        print("4. Вставьте его в переменную TOKEN в этом файле")
        return

    upload_folder = 'static/uploads'
    if not os.path.exists(upload_folder):
        print(f"❌ Папка {upload_folder} не найдена!")
        return

    # Получаем все изображения
    images = [f for f in os.listdir(upload_folder)
              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]

    print(f"📸 Найдено {len(images)} изображений")

    # URL для загрузки в Vercel Blob
    url = "https://blob.vercel-storage.com/upload"

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/octet-stream"
    }

    urls = {}

    for filename in images:
        filepath = os.path.join(upload_folder, filename)

        try:
            print(f"📤 Загрузка: {filename}...")

            with open(filepath, 'rb') as f:
                data = f.read()

            # Загружаем файл
            response = requests.post(
                url,
                headers=headers,
                data=data,
                params={"name": filename}
            )

            if response.status_code == 200:
                result = response.json()
                urls[filename] = result['url']
                print(f"✅ {filename} -> {result['url']}")
            else:
                print(f"❌ Ошибка загрузки {filename}: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"❌ Ошибка загрузки {filename}: {e}")

    # Сохраняем ссылки в файл
    with open('blob_urls.txt', 'w', encoding='utf-8') as f:
        for name, url in urls.items():
            # Создаем ключ для поиска (без расширения)
            key = os.path.splitext(name)[0]
            key = key.replace('-', ' ').replace('_', ' ')
            key = re.sub(r'\s+\d+$', '', key)
            f.write(f"{key} = {url}\n")

    print(f"\n✅ Загружено {len(urls)} изображений")
    print("📝 Ссылки сохранены в blob_urls.txt")
    return urls


if __name__ == '__main__':
    upload_images()