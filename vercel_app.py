# vercel_app.py - полная версия с вашим приложением
import sys
import os

# Добавляем текущую папку в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
import sqlite3
import re

# Создаем приложение
app = Flask(__name__)

# Настройки прямо здесь (без импорта config)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///thesaurus_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# ========== МОДЕЛИ ==========
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Word(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), nullable=False, index=True)
    definition = db.Column(db.Text, nullable=False)
    etymology = db.Column(db.Text)
    translation_en = db.Column(db.String(200))
    definition_en = db.Column(db.Text)
    example_uz = db.Column(db.Text)
    example_en = db.Column(db.Text)
    pronunciation = db.Column(db.String(100))
    part_of_speech_en = db.Column(db.String(50))
    etymology_en = db.Column(db.Text)
    image_url = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WordCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)


class WordSynonym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    related_word = db.Column(db.String(100), nullable=False, index=True)


class WordAntonym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    related_word = db.Column(db.String(100), nullable=False, index=True)


class WordHyperonym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    related_word = db.Column(db.String(100), nullable=False, index=True)


class WordHyponym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    related_word = db.Column(db.String(100), nullable=False, index=True)


class WordHolonym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    related_word = db.Column(db.String(100), nullable=False, index=True)


class WordMeronym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    related_word = db.Column(db.String(100), nullable=False, index=True)


class WordHomonym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    related_word = db.Column(db.String(100), nullable=False, index=True)


class WordParonym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    related_word = db.Column(db.String(100), nullable=False, index=True)


class WordUsageArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    area = db.Column(db.String(100), nullable=False, index=True)


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(200))
    visited_at = db.Column(db.DateTime, default=datetime.utcnow)
    page = db.Column(db.String(100))


class UserVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), unique=True)
    first_visit = db.Column(db.DateTime, default=datetime.utcnow)
    last_visit = db.Column(db.DateTime, default=datetime.utcnow)
    visit_count = db.Column(db.Integer, default=1)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ========== ИНИЦИАЛИЗАЦИЯ БД ==========
def init_db():
    """Создает базу данных и импортирует данные при первом запуске"""
    with app.app_context():
        db.create_all()

        # Проверяем, есть ли данные
        if Word.query.count() == 0:
            print("📁 Инициализация базы данных...")

            # Создаем админа
            if not User.query.filter_by(username='admin').first():
                admin = User(
                    username='admin',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ Админ создан")

            # Импортируем данные из JSON
            json_path = os.path.join(os.path.dirname(__file__), 'yangi.json')
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    imported = 0
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
                        turkum = item.get('turkumi', '') or item.get('part_of_speech_uz', '')
                        if turkum:
                            for cat in str(turkum).split(','):
                                cat = cat.strip()
                                if cat:
                                    db.session.add(WordCategory(word_id=word.id, category=cat))

                        imported += 1

                        if imported % 50 == 0:
                            db.session.commit()

                    db.session.commit()
                    print(f"✅ Импортировано {imported} слов")

                except Exception as e:
                    print(f"⚠️ Ошибка импорта: {e}")
            else:
                print("⚠️ Файл yangi.json не найден")

            print("✅ Инициализация завершена")


# ========== РОУТЫ ==========
@app.route('/')
def index():
    try:
        words_count = Word.query.count()
        return jsonify({
            'status': 'ok',
            'message': 'Сервер работает на Vercel!',
            'words_count': words_count,
            'version': '1.0.0'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})


@app.route('/debug')
def debug():
    try:
        files = os.listdir('.')
        return jsonify({
            'files': files[:20],
            'cwd': os.getcwd(),
            'words_count': Word.query.count(),
            'db_exists': os.path.exists('thesaurus_data.db')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats')
def stats():
    try:
        total_words = Word.query.filter(Word.word.notlike('_category_placeholder_%')).count()
        total_categories = db.session.query(WordCategory.category).distinct().count()

        return jsonify({
            'total_words': total_words,
            'total_categories': total_categories
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ========== ИНИЦИАЛИЗАЦИЯ ПРИ ЗАПУСКЕ ==========
with app.app_context():
    init_db()

# Экспортируем для Vercel
application = app