# vercel_app.py
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import sys

# Создаем приложение
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'

# Настраиваем базу данных
db_path = os.path.join(os.path.dirname(__file__), 'thesaurus_data.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
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


class WordCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)


# ========== ИНИЦИАЛИЗАЦИЯ БД ==========
def init_db():
    """Создает базу данных и импортирует данные"""
    with app.app_context():
        # Создаем таблицы
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

                    count = 0
                    for item in data[:100]:  # Первые 100 слов для быстрого теста
                        word_text = item.get('uzbek', '')
                        if not word_text:
                            continue

                        if Word.query.filter(Word.word.ilike(word_text)).first():
                            continue

                        word = Word(
                            word=word_text,
                            definition=item.get('Izohi', '') or item.get('definition_uz', '') or "Ta'rif mavjud emas",
                            etymology=item.get('Etimologiyasi', ''),
                            translation_en=item.get('Tarjimasi (ingliz tili)', '')
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

                except Exception as e:
                    print(f"⚠️ Ошибка импорта: {e}")
            else:
                print("⚠️ Файл yangi.json не найден")

            print("✅ Инициализация завершена")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ========== РОУТЫ ==========
@app.route('/')
def index():
    try:
        words_count = Word.query.count()
        return jsonify({
            'status': 'ok',
            'message': 'Сервер работает!',
            'words_count': words_count
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
            'files': files[:10],
            'words_count': Word.query.count(),
            'cwd': os.getcwd(),
            'db_exists': os.path.exists('thesaurus_data.db')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Инициализируем БД при загрузке
with app.app_context():
    init_db()

# Экспортируем для Vercel
app = app