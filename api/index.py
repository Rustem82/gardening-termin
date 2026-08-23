# api/index.py
import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app


# Инициализация БД при первом запуске
def initialize_database():
    """Инициализирует базу данных при первом запуске"""
    db_path = 'thesaurus_data.db'

    if not os.path.exists(db_path):
        from models import db, User
        from werkzeug.security import generate_password_hash

        with app.app_context():
            db.create_all()

            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()


# Вызываем инициализацию
initialize_database()

# Экспортируем для Vercel
handler = app