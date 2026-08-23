import os
import re
from pathlib import Path

import vercel_blob.blob_store as vb_store

from app import app
from models import db, Word


UPLOAD_DIR = Path("static/uploads")


def normalize_name(value: str) -> str:
    """
    Нормализация имени файла/термина для сопоставления.
    """
    if not value:
        return ""

    value = value.lower().strip()

    # Апострофы узбекского языка
    value = (
        value.replace("‘", "'")
        .replace("’", "'")
        .replace("`", "'")
        .replace("ʻ", "'")
    )

    # Убираем расширение
    value = re.sub(
        r"\.(jpg|jpeg|png|webp|gif|svg)$",
        "",
        value,
        flags=re.IGNORECASE
    )

    # Убираем возможные числовые суффиксы
    value = re.sub(r"[_\-\s]+v?\d+$", "", value)

    # Дефисы и подчёркивания -> пробел
    value = value.replace("_", " ").replace("-", " ")

    # Убираем содержимое в скобках для дополнительного сопоставления
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value)

    # Убираем лишние символы, но сохраняем буквы/цифры/апостроф
    value = re.sub(r"[^\w\s']", " ", value, flags=re.UNICODE)

    value = re.sub(r"\s+", " ", value).strip()

    return value


def get_result_url(result):
    """
    Поддерживает и dict, и объектный ответ разных версий vercel_blob.
    """
    if result is None:
        return None

    if isinstance(result, dict):
        return result.get("url")

    return getattr(result, "url", None)


def upload_all():
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")

    if not token:
        print("❌ BLOB_READ_WRITE_TOKEN не найден.")
        return

    if not token.startswith("vercel_blob_rw_"):
        print("❌ BLOB_READ_WRITE_TOKEN имеет неправильный формат.")
        return

    if not UPLOAD_DIR.exists():
        print(f"❌ Папка не найдена: {UPLOAD_DIR}")
        return

    image_files = sorted(
        [
            f
            for f in UPLOAD_DIR.iterdir()
            if f.is_file()
            and f.suffix.lower() in {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
                ".svg",
            }
        ],
        key=lambda x: x.name.lower(),
    )

    print("=" * 70)
    print("ЗАГРУЗКА ИЗОБРАЖЕНИЙ В VERCEL BLOB")
    print("=" * 70)
    print(f"Найдено изображений: {len(image_files)}")

    uploaded = 0
    failed = 0
    linked = 0
    word_not_found = 0

    with app.app_context():

        # Создаём карту терминов
        words = Word.query.all()

        word_map = {}

        for word in words:
            key = normalize_name(word.word)

            if key and key not in word_map:
                word_map[key] = word

        print(f"Терминов в БД: {len(words)}")
        print("-" * 70)

        for index, filepath in enumerate(image_files, start=1):

            filename = filepath.name
            image_key = normalize_name(filename)

            try:
                print(
                    f"[{index}/{len(image_files)}] "
                    f"📤 {filename}",
                    end=" ... ",
                    flush=True,
                )

                with open(filepath, "rb") as f:
                    file_data = f.read()

                # addRandomSuffix=False:
                # сохраняем нормальное имя файла без случайного суффикса
                result = vb_store.put(
                    filename,
                    file_data,
                    {
                        "addRandomSuffix": False
                    }
                )

                public_url = get_result_url(result)

                if not public_url:
                    print("❌ URL не получен")
                    failed += 1
                    continue

                uploaded += 1

                # Сопоставляем с термином
                word = word_map.get(image_key)

                # Если точного совпадения нет — пробуем мягкий поиск
                if not word:
                    candidates = [
                        w
                        for key, w in word_map.items()
                        if image_key
                        and (
                            key == image_key
                            or key.startswith(image_key)
                            or image_key.startswith(key)
                        )
                    ]

                    if len(candidates) == 1:
                        word = candidates[0]

                if word:
                    word.image_url = public_url
                    linked += 1

                    print(f"✅ {word.word}")
                else:
                    word_not_found += 1
                    print("⚠️ термин не найден")

                # Сохраняем частями
                if index % 25 == 0:
                    db.session.commit()
                    print(
                        f"   💾 Промежуточное сохранение: "
                        f"{index}/{len(image_files)}"
                    )

            except Exception as e:
                failed += 1
                print(f"❌ {e}")

        db.session.commit()

    print()
    print("=" * 70)
    print("ГОТОВО")
    print("=" * 70)
    print(f"Всего изображений:       {len(image_files)}")
    print(f"Успешно загружено:       {uploaded}")
    print(f"Ошибок загрузки:         {failed}")
    print(f"Привязано к терминам:    {linked}")
    print(f"Термин не найден:        {word_not_found}")
    print("=" * 70)


if __name__ == "__main__":
    upload_all()