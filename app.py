from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_login import LoginManager, current_user
from config import Config
from models import db, Word, WordCategory, WordSynonym, WordAntonym, WordHyperonym, WordHyponym, WordHolonym, \
    WordMeronym, WordHomonym, WordParonym, WordUsageArea, Visit, UserVisit
from admin import admin_bp, create_admin
from datetime import datetime
import os
import sqlite3

app = Flask(__name__)
app.config.from_object(Config)

# Инициализация базы данных
db.init_app(app)

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin.login'


@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))


# Регистрация blueprint для админки
app.register_blueprint(admin_bp)


# ========== ФУНКЦИЯ ПРИНУДИТЕЛЬНОГО ОБНОВЛЕНИЯ СТРУКТУРЫ БАЗЫ ==========
def ensure_new_columns():
    """Проверяет существование новых колонок и при необходимости пересоздаёт таблицы."""
    try:
        with app.app_context():
            conn = sqlite3.connect(Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', ''))
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(word)")
            columns = [col[1] for col in cursor.fetchall()]
            conn.close()

            if 'definition_en' not in columns:
                print("⚠️ Обнаружена устаревшая структура базы. Пересоздание таблиц...")
                with app.app_context():
                    db.drop_all()
                    db.create_all()
                    create_admin()
                print("✅ База данных пересоздана с новой структурой.")
            else:
                print("✅ Структура базы данных актуальна.")
    except Exception as e:
        print(f"⚠️ Ошибка при проверке структуры: {e}")
        with app.app_context():
            db.drop_all()
            db.create_all()
            create_admin()


with app.app_context():
    db.create_all()
    # ensure_new_columns()  # Раскомментируйте, если нужно пересоздать таблицы при обновлении структуры


@app.before_request
def track_visit():
    pass


@app.route('/')
def index():
    letter = request.args.get('letter', '').upper()
    alphabet = ['A', 'B', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'X', 'Y', 'Z',
                "O'", "G'", 'SH', 'CH', 'NG']

    words = []
    selected_letter = None

    if letter and letter in alphabet:
        selected_letter = letter
        words = Word.query.filter(Word.word.startswith(letter)).order_by(Word.word).all()

    try:
        popular_words = [w.word for w in Word.query.order_by(Word.word).limit(5).all()]
    except Exception:
        popular_words = ['tuproq', 'suv', "o'simlik", 'hosil', 'yer']

    return render_template('index.html',
                           popular_words=popular_words,
                           words=words,
                           selected_letter=selected_letter,
                           alphabet=alphabet)


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    results = []

    if query:
        try:
            # Ищем по названию слова ИЛИ по области применения
            words = Word.query.filter(
                (Word.word.ilike(f'%{query.lower()}%')) |
                (Word.usage_areas.any(WordUsageArea.area.ilike(f'%{query}%'))),
                ~Word.word.startswith('_category_placeholder_')
            ).all()

            # Сортировка: точное совпадение слова, начало слова, затем остальные
            def sort_words(word_obj):
                word_lower = word_obj.word.lower()
                query_lower = query.lower()
                if word_lower == query_lower:
                    return (0, word_lower)
                elif word_lower.startswith(query_lower):
                    return (1, word_lower)
                else:
                    return (2, word_lower)

            words = sorted(words, key=sort_words)

            for word in words:
                results.append({
                    'word': word.word,
                    'part_of_speech_uz': word.categories[0].category if word.categories.count() > 0 else '',
                    'definition_uz': word.definition,
                    'etymology_uz': word.etymology,
                    'example_uz': word.example_uz,
                    'field_uz': [area.area for area in word.usage_areas],
                    'synonyms_uz': [syn.related_word for syn in word.synonyms],
                    'english': word.translation_en,
                    'part_of_speech_en': word.part_of_speech_en,
                    'pronunciation': word.pronunciation,
                    'definition_en': word.definition_en,
                    'etymology_en': word.etymology_en,
                    'example_en': word.example_en,
                    'field_en': [area.area for area in word.usage_areas],
                    'synonyms_en': [syn.related_word for syn in word.synonyms],
                    'антонимы': [ant.related_word for ant in word.antonyms],
                    'гиперонимы': [hyp.related_word for hyp in word.hyperonyms],
                    'гипонимы': [hypo.related_word for hypo in word.hyponyms],
                    'xolonim': [hol.related_word for hol in word.holonyms],
                    'meronim': [mer.related_word for mer in word.meronyms],
                    'omonim': [hom.related_word for hom in word.homonyms],
                    'paronim': [par.related_word for par in word.paronyms],
                    'image_url': word.image_url
                })

        except Exception as e:
            print(f"Search error: {e}")
            results = []

    return render_template('search.html', query=query, results=results)

@app.route('/word/<word>')
def word_detail(word):
    try:
        db_word = Word.query.filter(Word.word.ilike(word)).first()
        if db_word:
            data = {
                'определение': db_word.definition,  # definition_uz
                'translation_en': db_word.translation_en,  # english
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
            return render_template('word_detail.html', word=db_word.word, data=data)
    except Exception:
        pass
    return render_template('404.html'), 404


@app.route('/categories')
def categories():
    try:
        cats = db.session.query(WordCategory.category).distinct().order_by(WordCategory.category).all()
        categories = [cat[0] for cat in cats]
    except Exception:
        categories = []
    return render_template('categories.html', categories=categories)

@app.route('/fields')
def fields_list():
    # Список всех областей (в том же формате, как вы указали)
    fields = [
        {"name": "Agronomiya", "en": "Agronomy"},
        {"name": "Agrobiologik asoslar", "en": "Agrobiological Foundations"},
        {"name": "Bog‘dorchilik", "en": "Horticulture"},
        {"name": "Ko‘chatchilik", "en": "Nursery Science"},
        {"name": "Manzarali bog‘dorchilik", "en": "Ornamental Horticulture"},
        {"name": "Mevachilik", "en": "Pomology"},
        {"name": "Seleksiya va genetika", "en": "Plant Breeding and Genetics"},
        {"name": "O‘simliklarni himoya qilish", "en": "Plant Protection"},
        {"name": "Sabzavotchilik", "en": "Olericulture"},
        {"name": "Uzumchilik", "en": "Viticulture"}
    ]
    return render_template('fields.html', fields=fields)

@app.route('/field/<field_name>')
def field_page(field_name):
    # Ищем слова, у которых область применения совпадает с введённой
    words = Word.query.filter(
        Word.usage_areas.any(WordUsageArea.area.ilike(f'%{field_name}%')),
        ~Word.word.startswith('_category_placeholder_')
    ).order_by(Word.word).all()

    return render_template('field_page.html', field_name=field_name, words=words)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').lower().strip()
    suggestions = []
    if query and len(query) >= 2:
        try:
            words = Word.query.filter(Word.word.ilike(f'%{query}%')).limit(10).all()
            suggestions = [word.word for word in words]
        except Exception:
            suggestions = []
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
                'image_url': word.image_url   # <--- ДОБАВЛЕНО
            })
    except Exception:
        pass
    return jsonify({'word': None})


@app.route('/api/stats')
def get_stats():
    try:
        from sqlalchemy import func

        total_records = Word.query.filter(Word.word.notlike('_category_placeholder_%')).count()
        unique_words = db.session.query(Word.word).distinct().filter(
            Word.word.notlike('_category_placeholder_%')).count()

        total_categories = db.session.query(WordCategory.category).distinct().count()
        total_synonyms = WordSynonym.query.count()

        top_categories = [
            {"name": "Ot", "count": 4156},
            {"name": "Sifat", "count": 315},
            {"name": "Birikmali terminlar", "count": 383},
            {"name": "Fe'l", "count": 247},
            {"name": "Sifat/ot shaklidagi terminlar", "count": 22}
        ]

        print(f"📊 API Stats: total_records={total_records}, unique_words={unique_words}")
        print(f"📊 Top categories: {top_categories}")

    except Exception as e:
        print(f"Error in /api/stats: {e}")
        total_records = 0
        unique_words = 0
        total_categories = 0
        total_synonyms = 0
        top_categories = [{"name": "Ma'lumot yo'q", "count": 0}]

    return jsonify({
        'total_words': total_records,
        'unique_words': unique_words,
        'total_categories': total_categories,
        'total_synonyms': total_synonyms,
        'total_visitors': 0,
        'today_visitors': 0,
        'active_visitors': 0,
        'growth': 0,
        'top_categories': top_categories
    })


@app.route('/stats/agriculture')
def agriculture_stats():
    """Маршрут для статистики по сельскому хозяйству"""
    import json
    import os
    from collections import Counter

    # Загружаем данные из JSON
    try:
        with open('tabl.json', 'r', encoding='utf-8') as f:
            words = json.load(f)
        print(f"✅ Загружен файл: tabl.json, слов: {len(words)}")
    except FileNotFoundError:
        try:
            with open('yangi.json', 'r', encoding='utf-8') as f:
                words = json.load(f)
            print(f"✅ Загружен файл: yangi.json, слов: {len(words)}")
        except:
            words = []
            print("❌ Файл не найден")

    # Если нет данных
    if not words:
        empty_data = [{'name': "JSON fayl topilmadi", 'count': 0, 'percentage': 0}]
        return render_template('agriculture_stats.html',
                               stats={'total_words': 0, 'general': empty_data},
                               active_tab=request.args.get('tab', 'general'))

    # Убираем служебные записи
    valid_words = [w for w in words if not w.get('uzbek', '').startswith('_category_placeholder_')]
    total = len(valid_words)

    print(f"📊 Всего валидных слов: {total}")

    # Функция для безопасного вычисления процента
    def safe_percentage(count, total):
        if total == 0:
            return 0
        return round(count / total * 100, 1)

    # ====== 1. ОБЩАЯ СТАТИСТИКА ПО СОХАЛЯМ ======
    # ИСПОЛЬЗУЕМ ТОЛЬКО field_uz
    field_counter = Counter()

    for w in valid_words:
        # Берем только узбекское поле
        field = w.get('field_uz', '')
        if field:
            # Берем первую часть до стрелки
            if '→' in field:
                main_field = field.split('→')[0].strip()
            else:
                main_field = field.strip()

            # Исключаем английские названия
            if main_field and main_field not in ['Horticulture', 'Agronomy', 'Plant Protection', 'Pomology',
                                                 'Viticulture', 'Olericulture', 'Nursery Science',
                                                 'Ornamental Horticulture', 'Plant Breeding and Genetics',
                                                 'Agrobiological Foundations']:
                field_counter[main_field] += 1

    # Формируем данные для общей статистики
    general_data = []
    for name, count in field_counter.most_common():
        general_data.append({
            'name': name,
            'count': count,
            'percentage': safe_percentage(count, total)
        })

    if not general_data:
        general_data = [{'name': "Ma'lumotlar mavjud emas", 'count': 0, 'percentage': 0}]

    print(f"📊 Общая статистика: {len(general_data)} записей")

    # ====== 2. СТАТИСТИКА ПО КОНКРЕТНЫМ СОХАМ ======
    # Список соха - ТОЛЬКО УЗБЕКСКИЕ НАЗВАНИЯ
    fields = [
        ('agronomiya', 'Agronomiya'),
        ('agrobiologik', 'Agrobiologik asoslar'),
        ('bogdorchilik', "Bog'dorchilik"),
        ('kochatchilik', "Ko'chatchilik"),
        ('manzarali', "Manzarali bog'dorchilik"),
        ('mevachilik', 'Mevachilik'),
        ('seleksiya', "Seleksiya va genetika"),
        ('himoya', "O'simliklarni himoya qilish"),
        ('sabzavotchilik', 'Sabzavotchilik'),
        ('uzumchilik', 'Uzumchilik')
    ]

    field_data = {}

    for key, field_name in fields:
        counter = Counter()

        for w in valid_words:
            # Берем только узбекское поле
            field = w.get('field_uz', '')
            if not field:
                continue

            # Проверяем, содержится ли название сохи в поле
            if field_name.lower() in field.lower():
                # Извлекаем подкатегорию (вторую часть после стрелки)
                if '→' in field:
                    parts = field.split('→')
                    if len(parts) > 1:
                        subfield = parts[1].strip()
                    else:
                        subfield = parts[0].strip()
                else:
                    subfield = field.strip()

                if subfield:
                    counter[subfield] += 1

        # Форматируем данные
        result = []
        for name, count in counter.most_common():
            result.append({
                'name': name,
                'count': count,
                'percentage': safe_percentage(count, total)
            })

        if not result:
            result = [{'name': "Ma'lumotlar mavjud emas", 'count': 0, 'percentage': 0}]

        field_data[key] = result
        print(f"📊 {field_name}: {len(result)} подкатегорий, всего слов: {sum(r['count'] for r in result)}")

    # ====== 3. СТАТИСТИКА ПО ТИПАМ СЛОВ ======
    word_types = {
        "Ot": 0,
        "Sifat": 0,
        "Fe'l": 0,
        "Birikmali terminlar": 0,
        "Sifat/ot shaklidagi terminlar": 0,
        "Ibora va frazeologik birliklar": 0,
        "Ravish": 0,
        "Yordamchi birliklar": 0,
        "Undov": 0
    }

    for w in valid_words:
        pos = w.get('part_of_speech_uz', '').lower()
        if 'ot' in pos and 'birikma' not in pos:
            word_types["Ot"] += 1
        elif 'sifat' in pos:
            word_types["Sifat"] += 1
        elif "fe'l" in pos or "fe’l" in pos:
            word_types["Fe'l"] += 1
        elif 'birikma' in pos:
            word_types["Birikmali terminlar"] += 1
        elif 'ravish' in pos:
            word_types["Ravish"] += 1
        elif 'undov' in pos:
            word_types["Undov"] += 1
        elif 'ibora' in pos or 'frazeologik' in pos:
            word_types["Ibora va frazeologik birliklar"] += 1
        elif 'yordamchi' in pos:
            word_types["Yordamchi birliklar"] += 1

    word_types_data = []
    for name, count in word_types.items():
        if count > 0:
            word_types_data.append({
                'name': name,
                'count': count,
                'percentage': safe_percentage(count, total)
            })
    word_types_data.sort(key=lambda x: x['count'], reverse=True)

    if not word_types_data:
        word_types_data = [{'name': "Ma'lumotlar mavjud emas", 'count': 0, 'percentage': 0}]

    # ====== 4. ТЕРМИН ТУРЛАРИ ======
    term_types_data = [
        {'name': "Tub (sodda) so'zlar", 'count': 2112, 'percentage': safe_percentage(2112, total)},
        {'name': "Yasama so'zlar (ildiz + affiks)", 'count': 1305, 'percentage': safe_percentage(1305, total)},
        {'name': "Qo'shma so'zlar", 'count': 729, 'percentage': safe_percentage(729, total)},
        {'name': "Birikmali terminlar", 'count': 770, 'percentage': safe_percentage(770, total)},
        {'name': "O'zlashma terminlar", 'count': 200, 'percentage': safe_percentage(200, total)},
        {'name': "Qisqartma va boshqa birliklar", 'count': 20, 'percentage': safe_percentage(20, total)}
    ]

    # ====== 5. ГИПЕРОНИМЫ ======
    def collect_relations(words, field_name):
        counter = Counter()
        for w in words:
            items = w.get(field_name, [])
            if isinstance(items, str):
                if ',' in items:
                    items = [i.strip() for i in items.split(',') if i.strip()]
                else:
                    items = [items] if items and items.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-',
                                                                       '—'] else []
            if isinstance(items, list):
                for item in items:
                    if item and item.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-', '—']:
                        counter[item] += 1
        return counter

    def format_relation_data(counter, total, limit=10):
        result = []
        for name, count in counter.most_common(limit):
            if name:
                result.append({
                    'name': name,
                    'count': count,
                    'percentage': safe_percentage(count, total)
                })
        if not result:
            result = [{'name': "Ma'lumotlar mavjud emas", 'count': 0, 'percentage': 0}]
        return result

    hyperonym_counter = collect_relations(valid_words, 'hyperonyms')
    hyponym_counter = collect_relations(valid_words, 'hyponyms')
    holonym_counter = collect_relations(valid_words, 'holonyms')
    meronym_counter = collect_relations(valid_words, 'meronyms')

    hyperonyms_data = format_relation_data(hyperonym_counter, total)
    hyponyms_data = format_relation_data(hyponym_counter, total)
    holonyms_data = format_relation_data(holonym_counter, total)
    meronyms_data = format_relation_data(meronym_counter, total)

    # ====== 6. СИНОНИМЫ ======
    with_synonyms = 0
    without_synonyms = 0
    for w in valid_words:
        synonyms = w.get('synonyms_uz', []) or w.get('sinonimi', [])
        if isinstance(synonyms, str):
            if ',' in synonyms:
                synonyms = [s.strip() for s in synonyms.split(',') if s.strip()]
            else:
                synonyms = [synonyms] if synonyms and synonyms.lower() not in ['-', 'yo\'q', 'yoq', 'нет', 'none',
                                                                               ''] else []
        if synonyms and synonyms != ["-"] and synonyms != ['']:
            with_synonyms += 1
        else:
            without_synonyms += 1

    synonyms_data = [
        {'name': "Sinonimi mavjud terminlar", 'count': with_synonyms,
         'percentage': safe_percentage(with_synonyms, total)},
        {'name': "Sinonimi berilmagan terminlar", 'count': without_synonyms,
         'percentage': safe_percentage(without_synonyms, total)}
    ]

    # ====== 7. АНТОНИМЫ ======
    with_antonyms = 0
    without_antonyms = 0
    for w in valid_words:
        antonyms = w.get('antonyms_uz', []) or w.get('antonimi', [])
        if isinstance(antonyms, str):
            if ',' in antonyms:
                antonyms = [a.strip() for a in antonyms.split(',') if a.strip()]
            else:
                antonyms = [antonyms] if antonyms and antonyms.lower() not in ['-', 'yo\'q', 'yoq', 'нет', 'none',
                                                                               ''] else []
        if antonyms and antonyms != ["-"] and antonyms != ['']:
            with_antonyms += 1
        else:
            without_antonyms += 1

    antonyms_data = [
        {'name': "Aniq antonimi mavjud", 'count': with_antonyms, 'percentage': safe_percentage(with_antonyms, total)},
        {'name': "Shartli / kontekstual antonim", 'count': 766, 'percentage': safe_percentage(766, total)},
        {'name': "Antonimi berilmagan (—, yo'q)", 'count': without_antonyms,
         'percentage': safe_percentage(without_antonyms, total)}
    ]

    # ====== 8. ОМОНИМЫ ======
    with_homonyms = 0
    without_homonyms = 0
    for w in valid_words:
        homonyms = w.get('homonyms', [])
        if isinstance(homonyms, str):
            if ',' in homonyms:
                homonyms = [h.strip() for h in homonyms.split(',') if h.strip()]
            else:
                homonyms = [homonyms] if homonyms and homonyms.lower() not in ['-', 'yo\'q', 'yoq', 'нет', 'none',
                                                                               ''] else []
        if homonyms and homonyms != ["-"] and homonyms != ['']:
            with_homonyms += 1
        else:
            without_homonyms += 1

    homonyms_data = [
        {'name': "Aniq omonim mavjud", 'count': with_homonyms, 'percentage': safe_percentage(with_homonyms, total)},
        {'name': "Fanlararo omonim", 'count': 0, 'percentage': 0},
        {'name': "Polisemiya (ko'p ma'nolilik)", 'count': 0, 'percentage': 0},
        {'name': "Omonimi mavjud emas", 'count': without_homonyms,
         'percentage': safe_percentage(without_homonyms, total)}
    ]

    # ====== 9. ИСТОЧНИКИ ОМОНИМИИ ======
    homonym_sources_data = [
        {'name': "Umumiy til ma'nosi ↔ terminologik ma'no", 'count': 4, 'percentage': safe_percentage(4, 9)},
        {'name': "Fanlararo omonimiya", 'count': 1, 'percentage': safe_percentage(1, 9)},
        {'name': "Ko'chma yoki badiiy ma'no", 'count': 2, 'percentage': safe_percentage(2, 9)},
        {'name': "Atama va nomlar to'qnashuvi", 'count': 2, 'percentage': safe_percentage(2, 9)},
        {'name': "Boshqa holatlar", 'count': 0, 'percentage': 0}
    ]

    # ====== 10. ПАРОНИМЫ ======
    with_paronyms = 0
    without_paronyms = 0
    for w in valid_words:
        paronyms = w.get('paronyms', [])
        if isinstance(paronyms, str):
            if ',' in paronyms:
                paronyms = [p.strip() for p in paronyms.split(',') if p.strip()]
            else:
                paronyms = [paronyms] if paronyms and paronyms.lower() not in ['-', 'yo\'q', 'yoq', 'нет', 'none',
                                                                               ''] else []
        if paronyms and paronyms != ["-"] and paronyms != ['']:
            with_paronyms += 1
        else:
            without_paronyms += 1

    paronyms_data = [
        {'name': "Aniq paronim juftligi mavjud", 'count': with_paronyms,
         'percentage': safe_percentage(with_paronyms, total)},
        {'name': "Fonetik-grafik yaqin paronimlar", 'count': 16, 'percentage': safe_percentage(16, total)},
        {'name': "Fanlararo paronimiya", 'count': 4, 'percentage': safe_percentage(4, total)},
        {'name': "Paronimi mavjud emas", 'count': without_paronyms,
         'percentage': safe_percentage(without_paronyms, total)}
    ]

    # Активная вкладка
    active_tab = request.args.get('tab', 'general')

    # Собираем все данные
    stats_data = {
        'total_words': total,
        'general': general_data,
        'word_types': word_types_data,
        'term_types': term_types_data,
        'hyperonyms': hyperonyms_data,
        'hyponyms': hyponyms_data,
        'holonyms': holonyms_data,
        'meronyms': meronyms_data,
        'synonyms': synonyms_data,
        'antonyms': antonyms_data,
        'homonyms': homonyms_data,
        'homonym_sources': homonym_sources_data,
        'paronyms': paronyms_data
    }

    # Добавляем данные для каждой сохи
    for key, name in fields:
        stats_data[key] = field_data[key]

    return render_template('agriculture_stats.html',
                           stats=stats_data,
                           active_tab=active_tab)


@app.route('/debug/simple')
def debug_simple():
    import json
    from collections import Counter

    try:
        with open('yangi.json', 'r', encoding='utf-8') as f:
            words = json.load(f)
    except Exception as e:
        return f"❌ Ошибка загрузки: {e}"

    # Простая проверка
    result = {
        'total': len(words),
        'first_word': words[0] if words else None,
        'field_uz_exists': 'field_uz' in words[0] if words else False,
        'field_uz_values': [w.get('field_uz', '') for w in words[:5]]
    }

    return result

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
        print(f"Error: {e}")
        pass
    return jsonify({'error': 'So\'z topilmadi'}), 404


@app.context_processor
def inject_globals():
    from models import Word, WordCategory, WordSynonym

    try:
        total_words = Word.query.count()
        total_categories = db.session.query(WordCategory.category).distinct().count()
        total_synonyms = WordSynonym.query.count()
    except Exception:
        total_words = total_categories = total_synonyms = 0

    return dict(
        is_admin=False,
        current_user=None,
        total_words=total_words,
        total_categories=total_categories,
        total_synonyms=total_synonyms
    )


@app.route('/debug/usage-check')
def debug_usage_check():
    from models import WordUsageArea, Word

    total = WordUsageArea.query.count()
    areas = WordUsageArea.query.limit(10).all()
    data = []
    for a in areas:
        word = Word.query.get(a.word_id)
        data.append({
            'word_id': a.word_id,
            'word': word.word if word else 'Unknown',
            'area': a.area
        })

    return jsonify({
        'total': total,
        'sample': data,
        'all_areas': list(set([a.area for a in WordUsageArea.query.all()]))
    })


@app.errorhandler(404)
def page_not_found(e):
    # Получаем путь, который запросил пользователь
    path = request.path
    word_query = None
    suggestions = []

    # Если это запрос к странице слова (/word/...)
    if path.startswith('/word/'):
        # Извлекаем слово из URL (убираем /word/ и декодируем пробелы)
        word_query = path.replace('/word/', '', 1).strip().lower()

        # Ищем в базе слова, похожие на введённое (содержат эту подстроку)
        if word_query:
            suggestions = Word.query.filter(
                Word.word.ilike(f'%{word_query}%'),
                ~Word.word.startswith('_category_placeholder_')  # Исключаем служебные
            ).limit(10).all()

    # Возвращаем шаблон 404 с найденными вариантами (и статус-код 404)
    return render_template('404.html', suggestions=suggestions, word_query=word_query), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500


@app.template_filter('numberformat')
def numberformat_filter(value):
    try:
        return f"{int(value):,}".replace(",", " ")
    except (ValueError, TypeError):
        return value


if __name__ == '__main__':
    app.run(debug=True)