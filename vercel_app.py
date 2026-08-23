# vercel_app.py - полная исправленная версия
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
import requests

# Создаем приложение
app = Flask(__name__)

# Настройки
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['INSTANCE_FOLDER'] = '/tmp'

# Путь к БД в /tmp (единственная записываемая папка на Vercel)
DB_PATH = '/tmp/thesaurus_data.db'

# Если БД нет в /tmp, скачиваем из Storage
if not os.path.exists(DB_PATH):
    try:
        # URL вашей БД из Storage
        BLOB_URL = "https://store_W6SAmavz4a8tGG7Q.blob.vercel-storage.com/thesaurus_data.db"
        print("📥 Скачивание БД из Storage...")
        response = requests.get(BLOB_URL, timeout=30)
        if response.status_code == 200:
            with open(DB_PATH, 'wb') as f:
                f.write(response.content)
            print("✅ БД загружена из Storage")
        else:
            print(f"❌ Не удалось загрузить БД: {response.status_code}")
            # Если не удалось скачать, используем локальную БД (если есть)
            local_db = os.path.join(os.path.dirname(__file__), 'thesaurus_data.db')
            if os.path.exists(local_db):
                import shutil
                shutil.copy2(local_db, DB_PATH)
                print("✅ Использована локальная БД")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки БД: {e}")
        # Если не удалось скачать, используем локальную БД (если есть)
        local_db = os.path.join(os.path.dirname(__file__), 'thesaurus_data.db')
        if os.path.exists(local_db):
            import shutil
            shutil.copy2(local_db, DB_PATH)
            print("✅ Использована локальная БД")

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'

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
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

                        turkum = item.get('turkumi', '') or item.get('part_of_speech_uz', '')
                        if turkum:
                            for cat in str(turkum).split(','):
                                cat = cat.strip()
                                if cat:
                                    db.session.add(WordCategory(word_id=word.id, category=cat))

                        imported += 1

                        if imported % 50 == 0:
                            db.session.commit()
                            print(f'✅ Добавлено {imported} слов...')

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
        files = os.listdir('/tmp')
        return jsonify({
            'files': files[:20],
            'cwd': os.getcwd(),
            'words_count': Word.query.count(),
            'db_exists': os.path.exists('/tmp/thesaurus_data.db')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/word/<word>')
def word_detail(word):
    try:
        db_word = Word.query.filter(Word.word.ilike(word)).first()
        if db_word:
            data = {
                'определение': db_word.definition,
                'translation_en': db_word.translation_en,
                'image_url': db_word.image_url,
                'turkumi': [cat.category for cat in db_word.categories],
                'синонимы': [syn.related_word for syn in db_word.synonyms]
            }
            # Проверяем, существует ли шаблон
            try:
                return render_template('word_detail.html', word=db_word.word, data=data)
            except:
                # Если шаблона нет, возвращаем JSON
                return jsonify({'word': db_word.word, 'data': data})
    except Exception as e:
        print(f"Error: {e}")
    return jsonify({'error': 'Word not found'}), 404

@app.route('/api/stats')
def stats():
    try:
        total = Word.query.count()
        return jsonify({
            'total_words': total
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== ИНИЦИАЛИЗАЦИЯ ПРИ ЗАПУСКЕ ==========
with app.app_context():
    init_db()

# Экспортируем для Vercel
application = app