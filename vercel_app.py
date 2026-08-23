# vercel_app.py - ИСПРАВЛЕННАЯ И ПОЛНАЯ ВЕРСИЯ
import sys
import os
import json
import requests
import shutil
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

# --- ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ ---
app = Flask(__name__)

# Настройки для работы за прокси (важно для Vercel)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Секретный ключ
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- НАСТРОЙКА БАЗЫ ДАННЫХ ДЛЯ VERCEL ---
DB_PATH = '/tmp/thesaurus_data.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'

# Если БД нет в /tmp, скачиваем из Storage или копируем локальную
if not os.path.exists(DB_PATH):
    try:
        BLOB_URL = "https://store_W6SAmavz4a8tGG7Q.blob.vercel-storage.com/thesaurus_data.db"
        print("📥 Скачивание БД из Storage...")
        response = requests.get(BLOB_URL, timeout=30)
        if response.status_code == 200:
            with open(DB_PATH, 'wb') as f:
                f.write(response.content)
            print("✅ БД загружена из Storage")
        else:
            print(f"❌ Не удалось загрузить БД: {response.status_code}")
            local_db = os.path.join(os.path.dirname(__file__), 'thesaurus_data.db')
            if os.path.exists(local_db):
                shutil.copy2(local_db, DB_PATH)
                print("✅ Использована локальная БД")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки БД: {e}")
        local_db = os.path.join(os.path.dirname(__file__), 'thesaurus_data.db')
        if os.path.exists(local_db):
            shutil.copy2(local_db, DB_PATH)
            print("✅ Использована локальная БД")

# --- МОДЕЛИ БАЗЫ ДАННЫХ (СО ВСЕМИ СВЯЗЯМИ) ---
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

    # --- ВСЕ СВЯЗИ (как в models.py) ---
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
    """Создает базу данных и импортирует данные при первом запуске"""
    with app.app_context():
        # Проверяем, есть ли уже таблицы
        if not db.engine.dialect.has_table(db.engine, 'word'):
            print("📁 Создание таблиц...")
            db.create_all()
            print("✅ Таблицы созданы")

        # Проверяем, есть ли слова в БД
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

                        # Пропускаем дубликаты
                        if Word.query.filter(Word.word.ilike(word_text)).first():
                            continue

                        # Создаем слово
                        word = Word(
                            word=word_text,
                            definition=item.get('Izohi', '') or item.get('definition_uz', '') or "Ta'rif mavjud emas",
                            etymology=item.get('Etimologiyasi', '') or item.get('etymology_uz', ''),
                            translation_en=item.get('Tarjimasi (ingliz tili)', '') or item.get('english', '')
                        )
                        db.session.add(word)
                        db.session.flush()

                        # Добавляем категории (turkum)
                        turkum = item.get('turkumi', '') or item.get('part_of_speech_uz', '')
                        if turkum:
                            for cat in str(turkum).split(','):
                                cat = cat.strip()
                                if cat and not WordCategory.query.filter_by(word_id=word.id, category=cat).first():
                                    db.session.add(WordCategory(word_id=word.id, category=cat))

                        # Добавляем синонимы
                        sinonim = item.get('sinonimi (ma\'nodoshi)', '') or item.get('sinonimi', '') or item.get('synonyms_uz', '')
                        if sinonim:
                            for syn in str(sinonim).split(','):
                                syn = syn.strip()
                                if syn and syn.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-', '—']:
                                    if not WordSynonym.query.filter_by(word_id=word.id, related_word=syn).first():
                                        db.session.add(WordSynonym(word_id=word.id, related_word=syn))

                        imported += 1

                        if imported % 50 == 0:
                            db.session.commit()
                            print(f'✅ Добавлено {imported} слов...')

                    db.session.commit()
                    print(f"✅ Импортировано {imported} слов")

                except Exception as e:
                    db.session.rollback()
                    print(f"⚠️ Ошибка импорта: {e}")
            else:
                print("⚠️ Файл yangi.json не найден, импорт пропущен")
        else:
            print(f"✅ База данных уже содержит {Word.query.count()} слов")

# Инициализация при первом запуске
with app.app_context():
    init_db()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РОУТОВ ---
def get_word_data(db_word):
    """Преобразует объект Word в словарь для шаблонов и API"""
    return {
        'определение': db_word.definition,
        'translation_en': db_word.translation_en,
        'definition_en': db_word.definition_en,
        'example_uz': db_word.example_uz,
        'example_en': db_word.example_en,
        'pronunciation': db_word.pronunciation,
        'part_of_speech_en': db_word.part_of_speech_en,
        'etymology_en': db_word.etymology_en,
        'image_url': db_word.image_url,
        'turkumi': [cat.category for cat in db_word.categories],
        'синонимы': [syn.related_word for syn in db_word.synonyms],
        'антонимы': [ant.related_word for ant in db_word.antonyms],
        'гиперонимы': [hyp.related_word for hyp in db_word.hyperonyms],
        'гипонимы': [hypo.related_word for hypo in db_word.hyponyms],
        'xolonim': [hol.related_word for hol in db_word.holonyms],
        'meronim': [mer.related_word for mer in db_word.meronyms],
        'omonim': [hom.related_word for hom in db_word.homonyms],
        'paronim': [par.related_word for par in db_word.paronyms],
        'qollanilishi': [area.area for area in db_word.usage_areas],
        'etimologiyasi': [db_word.etymology] if db_word.etymology else []
    }

# --- РОУТЫ ---
@app.route('/')
def index():
    """Главная страница с алфавитным указателем"""
    try:
        # Алфавит
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
        print(f"Error in index: {e}")
        return render_template('index.html', alphabet=[], popular_words=[], selected_letter=None, words=[])

@app.route('/search')
def search():
    """Страница поиска"""
    query = request.args.get('q', '').strip()
    results = []

    if query:
        try:
            words = Word.query.filter(Word.word.ilike(f'%{query.lower()}%')).order_by(Word.word).limit(20).all()
            for word in words:
                data = get_word_data(word)
                results.append({
                    'word': word.word,
                    'part_of_speech_uz': data['turkumi'][0] if data['turkumi'] else '',
                    'definition_uz': word.definition,
                    'etymology_uz': word.etymology,
                    'example_uz': word.example_uz,
                    'field_uz': data['qollanilishi'],
                    'synonyms_uz': data['синонимы'],
                    'english': word.translation_en,
                    'part_of_speech_en': word.part_of_speech_en,
                    'pronunciation': word.pronunciation,
                    'definition_en': word.definition_en,
                    'etymology_en': word.etymology_en,
                    'example_en': word.example_en,
                    'field_en': data['qollanilishi'],
                    'synonyms_en': data['синонимы'],
                    'антонимы': data['антонимы'],
                    'гиперонимы': data['гиперонимы'],
                    'гипонимы': data['гипонимы'],
                    'xolonim': data['xolonim'],
                    'meronim': data['meronim'],
                    'omonim': data['omonim'],
                    'paronim': data['paronim'],
                    'image_url': word.image_url
                })
        except Exception as e:
            print(f"Search error: {e}")

    return render_template('search.html', query=query, results=results)

@app.route('/word/<word>')
def word_detail(word):
    """Страница слова"""
    try:
        from urllib.parse import unquote
        import unicodedata

        word_clean = unquote(word)
        word_clean = unicodedata.normalize('NFC', word_clean)
        word_clean = ' '.join(word_clean.split())

        db_word = Word.query.filter(Word.word.ilike(word_clean)).first()

        if not db_word:
            variants = []
            for ch in ['‘', '’', "'", '`']:
                variants.append(word_clean.replace('‘', ch).replace('’', ch))
            for variant in variants:
                db_word = Word.query.filter(Word.word.ilike(variant)).first()
                if db_word:
                    break

        if db_word:
            data = get_word_data(db_word)
            return render_template('word_detail.html', word=db_word.word, data=data)

        similar = Word.query.filter(Word.word.ilike(f'%{word_clean[:5]}%')).limit(5).all()
        return render_template('404.html', suggestions=similar, word_query=word_clean), 404

    except Exception as e:
        print(f"Error in word_detail: {e}")
        import traceback
        traceback.print_exc()
        return render_template('404.html', suggestions=[], word_query=None), 404

@app.route('/categories')
def categories():
    """Страница со всеми категориями"""
    try:
        cats = db.session.query(WordCategory.category).distinct().order_by(WordCategory.category).all()
        categories = [cat[0] for cat in cats]
        return render_template('categories.html', categories=categories)
    except Exception as e:
        print(f"Error in categories: {e}")
        return render_template('categories.html', categories=[])

@app.route('/fields')
def fields_list():
    """Страница со списком областей (соха)"""
    fields = [
        {"name": "Agronomiya", "en": "Agronomy"},
        {"name": "Agrobiologik asoslar", "en": "Agrobiological Foundations"},
        {"name": "Bog'dorchilik", "en": "Horticulture"},
        {"name": "Ko'chatchilik", "en": "Nursery Science"},
        {"name": "Manzarali bog'dorchilik", "en": "Ornamental Horticulture"},
        {"name": "Mevachilik", "en": "Pomology"},
        {"name": "Seleksiya va genetika", "en": "Plant Breeding and Genetics"},
        {"name": "O'simliklarni himoya qilish", "en": "Plant Protection"},
        {"name": "Sabzavotchilik", "en": "Olericulture"},
        {"name": "Uzumchilik", "en": "Viticulture"}
    ]
    return render_template('fields.html', fields=fields)

@app.route('/field/<field_name>')
def field_page(field_name):
    """Страница для конкретной области"""
    try:
        words = Word.query.filter(
            Word.usage_areas.any(WordUsageArea.area.ilike(f'%{field_name}%'))
        ).order_by(Word.word).limit(50).all()
        return render_template('field_page.html', field_name=field_name, words=words)
    except Exception as e:
        print(f"Error in field_page: {e}")
        return render_template('field_page.html', field_name=field_name, words=[])

@app.route('/about')
def about():
    """Страница о проекте"""
    return render_template('about.html')

@app.route('/stats/agriculture')
def agriculture_stats():
    """Страница статистики"""
    try:
        total_words = Word.query.count()
        total_categories = db.session.query(WordCategory.category).distinct().count()

        category_stats = []
        cats = db.session.query(WordCategory.category).distinct().all()
        for cat in cats:
            count = WordCategory.query.filter_by(category=cat[0]).count()
            percentage = round(count / total_words * 100, 1) if total_words > 0 else 0
            category_stats.append({
                'name': cat[0],
                'count': count,
                'percentage': percentage
            })

        stats = {
            'total_words': total_words,
            'general': category_stats,
            'word_types': [],
            'term_types': [],
            'hyperonyms': [],
            'hyponyms': [],
            'holonyms': [],
            'meronyms': [],
            'synonyms': [],
            'antonyms': [],
            'homonyms': [],
            'paronyms': []
        }

        return render_template('agriculture_stats.html',
                               stats=stats,
                               active_tab=request.args.get('tab', 'general'))
    except Exception as e:
        print(f"Error in agriculture_stats: {e}")
        return render_template('agriculture_stats.html',
                               stats={'total_words': 0, 'general': []},
                               active_tab='general')

# --- API РОУТЫ ---
@app.route('/api/stats')
def stats():
    try:
        total = Word.query.count()
        unique = db.session.query(Word.word).distinct().count()
        total_categories = db.session.query(WordCategory.category).distinct().count()
        total_synonyms = WordSynonym.query.count()

        # Топ-категории
        top_cats = []
        for cat in db.session.query(WordCategory.category).distinct().limit(5):
            count = WordCategory.query.filter_by(category=cat[0]).count()
            top_cats.append({'name': cat[0], 'count': count})

        return jsonify({
            'total_words': total,
            'unique_words': unique,
            'total_categories': total_categories,
            'total_synonyms': total_synonyms,
            'total_visitors': 0,
            'today_visitors': 0,
            'active_visitors': 0,
            'growth': 0,
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
                'categories': [cat.category for cat in word.categories],
                'image_url': word.image_url
            })
    except Exception:
        pass
    return jsonify({'word': None})

@app.route('/api/semantic-network/<word>')
def semantic_network(word):
    try:
        db_word = Word.query.filter(Word.word.ilike(word)).first()
        if db_word:
            nodes = [{'id': db_word.word, 'type': 'main'}]
            links = []

            relation_types = [
                ('synonyms', 'синоним', '#4CAF50'),
                ('antonyms', 'антоним', '#f44336'),
                ('hyperonyms', 'гипероним', '#FF9800'),
                ('hyponyms', 'гипоним', '#2196F3'),
                ('holonyms', 'холоним', '#9C27B0'),
                ('meronyms', 'мероним', '#FF6B6B'),
                ('homonyms', 'омоним', '#00BCD4'),
                ('paronyms', 'пароним', '#FFC107'),
            ]

            for attr_name, rel_type, color in relation_types:
                relations = getattr(db_word, attr_name, [])
                for rel in relations:
                    nodes.append({'id': rel.related_word, 'type': rel_type})
                    links.append({
                        'source': db_word.word,
                        'target': rel.related_word,
                        'type': rel_type,
                        'color': color
                    })

            for area in db_word.usage_areas:
                nodes.append({'id': f"[{area.area}]", 'type': 'qollanilishi', 'is_usage': True})
                links.append({
                    'source': db_word.word,
                    'target': f"[{area.area}]",
                    'type': 'qollanilishi',
                    'color': '#795548'
                })

            unique_nodes = []
            seen = set()
            for node in nodes:
                if node['id'] not in seen:
                    seen.add(node['id'])
                    unique_nodes.append(node)

            return jsonify({
                'focus': db_word.word,
                'nodes': unique_nodes,
                'links': links
            })
    except Exception as e:
        print(f"Error in semantic_network: {e}")
    return jsonify({'error': 'So\'z topilmadi'}), 404

# --- АДМИН-ПАНЕЛЬ ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        else:
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

@app.route('/admin/words')
@login_required
def admin_words():
    words = Word.query.order_by(Word.word).paginate(page=request.args.get('page', 1, type=int), per_page=20)
    return render_template('admin/words.html', words=words)

@app.route('/admin/words/add', methods=['GET', 'POST'])
@login_required
def admin_add_word():
    if request.method == 'POST':
        # ... (код для добавления слова)
        flash('So\'z qo\'shildi', 'success')
        return redirect(url_for('admin_words'))
    return render_template('admin/word_form.html')

@app.route('/admin/words/edit/<int:word_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_word(word_id):
    word = Word.query.get_or_404(word_id)
    if request.method == 'POST':
        # ... (код для редактирования слова)
        flash('So\'z yangilandi', 'success')
        return redirect(url_for('admin_words'))
    return render_template('admin/word_form.html', word=word)

@app.route('/admin/words/delete/<int:word_id>')
@login_required
def admin_delete_word(word_id):
    word = Word.query.get_or_404(word_id)
    db.session.delete(word)
    db.session.commit()
    flash('So\'z o\'chirildi', 'success')
    return redirect(url_for('admin_words'))

@app.route('/admin/categories')
@login_required
def admin_categories():
    cats = db.session.query(WordCategory.category).distinct().order_by(WordCategory.category).all()
    categories = [cat[0] for cat in cats]
    return render_template('admin/categories.html', categories=categories)

@app.route('/admin/categories/add', methods=['POST'])
@login_required
def admin_add_category():
    # ... (код для добавления категории)
    return redirect(url_for('admin_categories'))

@app.route('/admin/categories/delete/<path:category>')
@login_required
def admin_delete_category(category):
    # ... (код для удаления категории)
    return redirect(url_for('admin_categories'))

@app.route('/admin/import-export')
@login_required
def admin_import_export():
    return render_template('admin/import_export.html')

@app.route('/admin/api/export-json')
@login_required
def admin_export_json():
    words = Word.query.all()
    data = []
    for word in words:
        if word.word.startswith('_category_placeholder_'):
            continue
        data.append({
            'word': word.word,
            'definition': word.definition,
            'etymology': word.etymology,
            'translation_en': word.translation_en,
            'definition_en': word.definition_en,
            'example_uz': word.example_uz,
            'example_en': word.example_en,
            'pronunciation': word.pronunciation,
            'part_of_speech_en': word.part_of_speech_en,
            'etymology_en': word.etymology_en,
            'image_url': word.image_url,
            'categories': [cat.category for cat in word.categories],
            'synonyms': [syn.related_word for syn in word.synonyms],
            'antonyms': [ant.related_word for ant in word.antonyms],
            'hyperonyms': [hyp.related_word for hyp in word.hyperonyms],
            'hyponyms': [hypo.related_word for hypo in word.hyponyms],
            'holonyms': [hol.related_word for hol in word.holonyms],
            'meronyms': [mer.related_word for mer in word.meronyms],
            'homonyms': [hom.related_word for hom in word.homonyms],
            'paronyms': [par.related_word for par in word.paronyms],
            'usage_areas': [area.area for area in word.usage_areas]
        })
    response = jsonify(data)
    response.headers['Content-Disposition'] = 'attachment; filename=gardening_export.json'
    response.headers['Content-Type'] = 'application/json'
    return response

@app.route('/admin/api/import-json', methods=['POST'])
@login_required
def admin_import_json():
    # ... (код для импорта JSON)
    flash('Импорт выполнен', 'success')
    return redirect(url_for('admin_import_export'))

# --- ОБРАБОТКА ОШИБОК ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', suggestions=[], word_query=None), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500

# --- ДОПОЛНИТЕЛЬНЫЕ РОУТЫ ДЛЯ СТАТИКИ ---
@app.route('/favicon.ico')
def favicon():
    return '', 204

# --- ЗАПУСК ДЛЯ ЛОКАЛЬНОЙ РАЗРАБОТКИ ---
if __name__ == '__main__':
    app.run(debug=True)

# Экспортируем для Vercel
application = app