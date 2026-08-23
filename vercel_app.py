# vercel_app.py - УПРОЩЕННАЯ РАБОЧАЯ ВЕРСИЯ
import sys
import os
import json
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

# --- СОЗДАНИЕ ПРИЛОЖЕНИЯ ---
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config['SECRET_KEY'] = 'dev-key-change-in-production'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- НАСТРОЙКА БАЗЫ ДАННЫХ ---
DB_PATH = os.path.join(os.path.dirname(__file__), 'thesaurus_data.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'

# --- МОДЕЛИ ---
db = SQLAlchemy(app)


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

    # Связи (relationships)
    categories = db.relationship('WordCategory', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    synonyms = db.relationship('WordSynonym', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    antonyms = db.relationship('WordAntonym', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    hyperonyms = db.relationship('WordHyperonym', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    hyponyms = db.relationship('WordHyponym', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    holonyms = db.relationship('WordHolonym', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    meronyms = db.relationship('WordMeronym', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    homonyms = db.relationship('WordHomonym', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    paronyms = db.relationship('WordParonym', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')
    usage_areas = db.relationship('WordUsageArea', backref='word_item', lazy='dynamic', cascade='all, delete-orphan')


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


# --- FLASK-LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    """Создает таблицы и добавляет тестовые данные"""
    with app.app_context():
        db.create_all()
        print("✅ Таблицы созданы")

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

        # Добавляем тестовые данные, если их нет
        if Word.query.count() == 0:
            print("📝 Добавление тестовых слов...")

            test_words = [
                {"word": "tuproq", "definition": "Yer po'stining yuza unumdor qatlami", "category": "ot"},
                {"word": "suv", "definition": "Rangsiz, hidsiz suyuqlik", "category": "ot"},
                {"word": "o'simlik", "definition": "Organizm, odatda tuproqda o'sadi", "category": "ot"},
                {"word": "hosil", "definition": "Ekinlardan olingan mahsulot", "category": "ot"},
                {"word": "yer", "definition": "Yer sayyorasining yuzasi", "category": "ot"},
            ]

            for item in test_words:
                word = Word(
                    word=item['word'],
                    definition=item['definition']
                )
                db.session.add(word)
                db.session.flush()

                # Добавляем категорию
                db.session.add(WordCategory(word_id=word.id, category=item['category']))

            db.session.commit()
            print(f"✅ Добавлено {len(test_words)} тестовых слов")


# Инициализация
with app.app_context():
    init_db()


# --- РОУТЫ ---
@app.route('/')
def index():
    """Главная страница"""
    try:
        alphabet = ['A', 'B', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                    'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'X', 'Y', 'Z',
                    "O'", "G'", 'SH', 'CH', 'NG']

        letter = request.args.get('letter', '').upper()
        words = []
        selected_letter = None

        if letter and letter in alphabet:
            selected_letter = letter
            words = Word.query.filter(Word.word.startswith(letter)).order_by(Word.word).limit(50).all()

        popular_words = [w.word for w in Word.query.order_by(Word.word).limit(5).all()]
        if not popular_words:
            popular_words = ['tuproq', 'suv', "o'simlik", 'hosil', 'yer']

        return render_template('index.html',
                               alphabet=alphabet,
                               popular_words=popular_words,
                               selected_letter=selected_letter,
                               words=words)
    except Exception as e:
        print(f"Index error: {e}")
        return f"Error: {e}", 500


@app.route('/word/<word>')
def word_detail(word):
    """Страница слова"""
    try:
        db_word = Word.query.filter(Word.word.ilike(word)).first()
        if db_word:
            data = {
                'определение': db_word.definition,
                'translation_en': db_word.translation_en,
                'image_url': db_word.image_url,
                'turkumi': [cat.category for cat in db_word.categories],
                'синонимы': [syn.related_word for syn in db_word.synonyms],
                'антонимы': [ant.related_word for ant in db_word.antonyms]
            }
            return render_template('word_detail.html', word=db_word.word, data=data)

        return render_template('404.html', suggestions=[], word_query=word), 404
    except Exception as e:
        print(f"Word detail error: {e}")
        return f"Error: {e}", 500


@app.route('/api/stats')
def stats():
    try:
        total = Word.query.count()
        total_categories = db.session.query(WordCategory.category).distinct().count()

        # Топ категории
        top_cats = []
        for cat in db.session.query(WordCategory.category).distinct().limit(5):
            count = WordCategory.query.filter_by(category=cat[0]).count()
            top_cats.append({'name': cat[0], 'count': count})

        return jsonify({
            'total_words': total,
            'total_categories': total_categories,
            'top_categories': top_cats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').lower().strip()
    suggestions = []
    if query and len(query) >= 2:
        try:
            words = Word.query.filter(Word.word.ilike(f'%{query}%')).limit(10).all()
            suggestions = [word.word for word in words]
        except Exception:
            pass
    return jsonify(suggestions)


@app.route('/api/random-word')
def random_word():
    import random
    try:
        words = Word.query.all()
        if words:
            word = random.choice(words)
            return jsonify({
                'word': word.word,
                'definition': word.definition[:200] + '...' if len(word.definition) > 200 else word.definition,
                'categories': [cat.category for cat in word.categories]
            })
    except Exception:
        pass
    return jsonify({'word': None})


# --- АДМИН-ПАНЕЛЬ (УПРОЩЕННАЯ) ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        return render_template('admin/login.html', error='Неверный логин или пароль')
    return render_template('admin/login.html')


@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    words_count = Word.query.count()
    total_categories = db.session.query(WordCategory.category).distinct().count()
    recent_words = Word.query.order_by(Word.created_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html',
                           words_count=words_count,
                           total_categories=total_categories,
                           recent_words=recent_words)


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    results = []
    if query:
        try:
            words = Word.query.filter(Word.word.ilike(f'%{query}%')).limit(20).all()
            for word in words:
                results.append({
                    'word': word.word,
                    'definition': word.definition,
                    'image_url': word.image_url
                })
        except Exception:
            pass
    return render_template('search.html', query=query, results=results)


@app.route('/categories')
def categories():
    try:
        cats = db.session.query(WordCategory.category).distinct().all()
        categories = [cat[0] for cat in cats]
        return render_template('categories.html', categories=categories)
    except Exception:
        return render_template('categories.html', categories=[])


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'words': Word.query.count()})


@app.route('/debug')
def debug():
    try:
        words_count = Word.query.count()
        return jsonify({
            'status': 'ok',
            'words_count': words_count,
            'db_path': DB_PATH,
            'db_exists': os.path.exists(DB_PATH)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- ОБРАБОТКА ОШИБОК ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', suggestions=[], word_query=None), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500


# --- ЗАПУСК ---
application = app

if __name__ == '__main__':
    app.run(debug=True)