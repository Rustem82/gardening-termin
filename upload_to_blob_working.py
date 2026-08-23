# upload_to_blob_working.py
import os
import re
from vercel_blob import put

# ВАШ ТОКЕН
TOKEN = "vercel_blob_rw_W6SAmavz4a8tGG7Q_kz6pt9SHHd3MrKK684ZghRp9qkcYQT"


def upload_images():
    upload_folder = 'static/uploads'
    if not os.path.exists(upload_folder):
        print(f"❌ Папка {upload_folder} не найдена!")
        return

    images = [f for f in os.listdir(upload_folder)
              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]

    print(f"📸 Найдено {len(images)} изображений")

    urls = {}

    for filename in images:
        filepath = os.path.join(upload_folder, filename)

        try:
            print(f"📤 Загрузка: {filename}...")

            with open(filepath, 'rb') as f:
                # Без параметра access
                result = put(filename, f.read())

                urls[filename] = result.url
                print(f"✅ {filename} -> {result.url}")

        except Exception as e:
            print(f"❌ Ошибка загрузки {filename}: {e}")

    with open('blob_urls.txt', 'w', encoding='utf-8') as f:
        for name, url in urls.items():
            key = os.path.splitext(name)[0]
            key = key.replace('-', ' ').replace('_', ' ')
            key = re.sub(r'\s+\d+$', '', key)
            f.write(f"{key} = {url}\n")

    print(f"\n✅ Загружено {len(urls)} изображений")
    print("📝 Ссылки сохранены в blob_urls.txt")
    return urls


if __name__ == '__main__':
    upload_images()