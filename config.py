# config.py
import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this'

    # Используем SQLite для Vercel (временная БД)
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        # Для локальной разработки
        SQLALCHEMY_DATABASE_URI = 'sqlite:///thesaurus_data.db'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Дополнительные настройки
    DEBUG = False
    TESTING = False