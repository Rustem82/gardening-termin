# vercel_db.py
import os
import sqlite3
from app import app, db
from models import Word, WordCategory, WordSynonym, WordAntonym, WordHyperonym, WordHyponym, WordHolonym, WordMeronym, \
    WordHomonym, WordParonym, WordUsageArea


def init_db():
    """Инициализирует базу данных для Vercel"""

    # Проверяем, существует ли файл БД
    db_path = 'thesaurus_data.db'

    if not os.path.exists(db_path):
        print("📁 Создание базы данных...")

        with app.app_context():
            # Создаем все таблицы
            db.create_all()

            # Добавляем админа
            from werkzeug.security import generate_password_hash
            from models import User

            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ Админ создан: admin/admin123")

            # Импортируем данные из JSON (если есть)
            import json
            try:
                with open('yangi.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)

                count = 0
                for item in data:
                    word_text = item.get('uzbek', '')
                    if not word_text:
                        continue

                    if Word.query.filter(Word.word.ilike(word_text)).first():
                        continue

                    word = Word(
                        word=word_text,
                        definition=item.get('Izohi', '') or item.get('definition_uz', '') or "Ta'rif mavjud emas",
                        etymology=item.get('Etimologiyasi', '') or item.get('etymology_uz', ''),
                        translation_en=item.get('Tarjimasi (ingliz tili)', '') or item.get('english', '')
                    )
                    db.session.add(word)
                    db.session.flush()

                    # Добавляем категории
                    turkum = item.get('turkumi', '')
                    if turkum:
                        for cat in str(turkum).split(','):
                            cat = cat.strip()
                            if cat:
                                db.session.add(WordCategory(word_id=word.id, category=cat))

                    count += 1

                    if count % 50 == 0:
                        db.session.commit()

                db.session.commit()
                print(f"✅ Импортировано {count} слов")

            except FileNotFoundError:
                print("⚠️ файл yangi.json не найден, импорт пропущен")
            except Exception as e:
                print(f"⚠️ Ошибка импорта: {e}")

        print("✅ База данных создана")
    else:
        print("✅ База данных уже существует")


if __name__ == '__main__':
    init_db()