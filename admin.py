from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Word, WordCategory, WordSynonym, WordAntonym, WordHyperonym, WordHyponym, WordHolonym, \
    WordMeronym, WordHomonym, WordParonym, WordUsageArea
from functools import wraps
from datetime import datetime
import os
import uuid
import re

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ========== НАСТРОЙКИ ДЛЯ ЗАГРУЗКИ ФАЙЛОВ ==========
UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}


def allowed_file(filename):
    """Проверяет разрешено ли расширение файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file, custom_name=None):
    """Сохраняет загруженное изображение и возвращает URL"""
    if file and allowed_file(file.filename):
        # Создаем уникальное имя файла или используем custom_name
        ext = file.filename.rsplit('.', 1)[1].lower()
        if custom_name:
            filename = f"{custom_name}.{ext}"
        else:
            filename = f"{uuid.uuid4().hex}.{ext}"

        # Создаем папку если её нет
        upload_path = os.path.join(current_app.root_path, UPLOAD_FOLDER)
        os.makedirs(upload_path, exist_ok=True)

        # Сохраняем файл
        filepath = os.path.join(upload_path, filename)
        file.save(filepath)

        # Возвращаем URL
        return f"/{UPLOAD_FOLDER}{filename}"
    return None


def delete_image(image_url):
    """Удаляет файл изображения если он существует"""
    if image_url and image_url.startswith('/static/uploads/'):
        filepath = os.path.join(current_app.root_path, image_url.lstrip('/'))
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                return True
            except:
                pass
    return False


def get_word_from_filename(filename):
    """Извлекает слово из имени файла"""
    # Удаляем расширение
    name = filename.rsplit('.', 1)[0]
    # Убираем возможные суффиксы типа _1, _2, _v2 и т.д.
    name = re.sub(r'[_\-]\d+$', '', name)
    name = re.sub(r'[_\-]v\d+$', '', name)
    # Заменяем _ и - на пробелы и приводим к нижнему регистру
    return name.replace('_', ' ').replace('-', ' ').lower().strip()


# ========== ФУНКЦИЯ ДЛЯ АВТОМАТИЧЕСКОЙ ПРИВЯЗКИ ИЗОБРАЖЕНИЙ ==========
def auto_link_images(words=None):
    """Автоматически привязывает изображения к словам по имени файла"""
    upload_path = os.path.join(current_app.root_path, UPLOAD_FOLDER)
    if not os.path.exists(upload_path):
        return 0, 0

    # Получаем все изображения в папке
    image_files = []
    for f in os.listdir(upload_path):
        if allowed_file(f):
            image_files.append(f)

    if not image_files:
        return 0, 0

    linked = 0
    skipped = 0

    for filename in image_files:
        # Проверяем, есть ли уже это изображение у какого-то слова
        existing = Word.query.filter(Word.image_url.like(f'%/{filename}')).first()
        if existing:
            skipped += 1
            continue

        # Извлекаем слово из имени файла
        word_text = get_word_from_filename(filename)

        # Ищем слово в базе (точное совпадение или начинается с)
        word = Word.query.filter(
            Word.word.ilike(f'{word_text}'),
            ~Word.word.startswith('_category_placeholder_')
        ).first()

        if not word:
            # Пробуем частичное совпадение
            word = Word.query.filter(
                Word.word.ilike(f'%{word_text}%'),
                ~Word.word.startswith('_category_placeholder_')
            ).first()

        if word:
            # Проверяем, не занято ли уже изображение
            if word.image_url:
                # Если у слова уже есть изображение, пропускаем
                skipped += 1
                continue

            # Привязываем изображение к слову
            word.image_url = f"/{UPLOAD_FOLDER}{filename}"
            linked += 1
            print(f"✅ Привязано изображение '{filename}' к слову '{word.word}'")

    if linked > 0:
        db.session.commit()

    return linked, skipped


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def add_unique_relation(word_id, relation_model, value, value_field='related_word'):
    if not value or not value.strip():
        return
    value = value.strip()
    existing = relation_model.query.filter_by(
        word_id=word_id,
        **{value_field: value}
    ).first()
    if not existing:
        db.session.add(relation_model(word_id=word_id, **{value_field: value}))


def add_unique_categories(word_id, categories):
    added = set()
    for cat in categories:
        cat = cat.strip()
        if cat and cat not in added:
            added.add(cat)
            existing = WordCategory.query.filter_by(word_id=word_id, category=cat).first()
            if not existing:
                db.session.add(WordCategory(word_id=word_id, category=cat))


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Bu sahifaga kirish uchun admin huquqlari kerak', 'danger')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)

    return decorated_function


@admin_bp.context_processor
def inject_now():
    return {'now': datetime.now}


@admin_bp.context_processor
def inject_admin_data():
    return {'words_count': Word.query.count()}


# ========== ЛОГИН И ВЫХОД ==========
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Xush kelibsiz!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Login yoki parol noto\'g\'ri', 'danger')
    return render_template('admin/login.html')


@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Tizimdan chiqdingiz', 'info')
    return redirect(url_for('admin.login'))


# ========== DASHBOARD ==========
@admin_bp.route('/')
@admin_required
def dashboard():
    words_count = Word.query.count()
    categories_count = db.session.query(WordCategory.category).distinct().count()
    total_synonyms = WordSynonym.query.count()

    categories = db.session.query(WordCategory.category).distinct().order_by(WordCategory.category).all()
    category_stats = []
    for cat in categories:
        cat_name = cat[0]
        count = WordCategory.query.filter_by(category=cat_name).count()
        percentage = (count / words_count * 100) if words_count > 0 else 0
        category_stats.append({
            'name': cat_name,
            'count': count,
            'percentage': round(percentage, 1)
        })

    recent_words = Word.query.order_by(Word.created_at.desc()).limit(5).all()

    return render_template('admin/dashboard.html',
                           words_count=words_count,
                           categories_count=categories_count,
                           total_synonyms=total_synonyms,
                           category_stats=category_stats,
                           recent_words=recent_words)


# ========== АВТОМАТИЧЕСКАЯ ЗАГРУЗКА ИЗОБРАЖЕНИЙ ==========
@admin_bp.route('/auto-link-images', methods=['GET', 'POST'])
@admin_required
def auto_link_images_route():
    if request.method == 'POST':
        linked, skipped = auto_link_images()
        flash(f'✅ {linked} ta rasm muvaffaqiyatli bog\'landi!', 'success')
        if skipped > 0:
            flash(f'ℹ️ {skipped} ta rasm allaqachon bog\'langan yoki mos kelmadi', 'info')
        return redirect(url_for('admin.dashboard'))

    # GET - показываем страницу с предпросмотром
    upload_path = os.path.join(current_app.root_path, UPLOAD_FOLDER)
    images = []
    if os.path.exists(upload_path):
        for f in os.listdir(upload_path):
            if allowed_file(f):
                word_text = get_word_from_filename(f)
                word = Word.query.filter(
                    Word.word.ilike(word_text),
                    ~Word.word.startswith('_category_placeholder_')
                ).first()
                images.append({
                    'filename': f,
                    'word': word_text,
                    'found_word': word.word if word else None,
                    'has_image': word and word.image_url
                })

    return render_template('admin/auto_link_images.html', images=images)


# ========== УПРАВЛЕНИЕ СЛОВАМИ ==========
@admin_bp.route('/words')
@admin_required
def words():
    page = request.args.get('page', 1, type=int)
    words = Word.query.order_by(Word.word).paginate(page=page, per_page=20)
    return render_template('admin/words.html', words=words)


@admin_bp.route('/words/add', methods=['GET', 'POST'])
@admin_required
def add_word():
    if request.method == 'POST':
        word_text = request.form.get('word', '').strip().lower()
        if not word_text:
            flash('So\'z kiritilmagan!', 'danger')
            return redirect(url_for('admin.add_word'))

        existing = Word.query.filter_by(word=word_text).first()
        if existing:
            flash(f'Bu so\'z allaqachon mavjud: "{word_text}"', 'warning')

        # Обработка изображения
        image_url = request.form.get('image_url', '').strip()
        image_file = request.files.get('image_file')

        # Если загружен файл, сохраняем его
        if image_file and allowed_file(image_file.filename):
            saved_url = save_image(image_file, word_text)
            if saved_url:
                image_url = saved_url
                flash('Rasm muvaffaqiyatli yuklandi!', 'success')
            else:
                flash('Rasm yuklashda xatolik yuz berdi', 'danger')

        word = Word(
            word=word_text,
            definition=request.form.get('definition', '').strip(),
            etymology=request.form.get('etymology', '').strip(),
            translation_en=request.form.get('translation_en', '').strip(),
            definition_en=request.form.get('definition_en', '').strip(),
            example_uz=request.form.get('example_uz', '').strip(),
            example_en=request.form.get('example_en', '').strip(),
            pronunciation=request.form.get('pronunciation', '').strip(),
            part_of_speech_en=request.form.get('part_of_speech_en', '').strip(),
            etymology_en=request.form.get('etymology_en', '').strip(),
            image_url=image_url
        )

        if not word.definition:
            flash('Ta\'rif kiritilmagan!', 'danger')
            return redirect(url_for('admin.add_word'))

        try:
            db.session.add(word)
            db.session.flush()

            add_unique_categories(word.id, request.form.getlist('categories[]'))
            for syn in request.form.getlist('synonyms[]'):
                add_unique_relation(word.id, WordSynonym, syn)
            for ant in request.form.getlist('antonyms[]'):
                add_unique_relation(word.id, WordAntonym, ant)
            for hyp in request.form.getlist('hyperonyms[]'):
                add_unique_relation(word.id, WordHyperonym, hyp)
            for hypo in request.form.getlist('hyponyms[]'):
                add_unique_relation(word.id, WordHyponym, hypo)
            for hol in request.form.getlist('holonyms[]'):
                add_unique_relation(word.id, WordHolonym, hol)
            for mer in request.form.getlist('meronyms[]'):
                add_unique_relation(word.id, WordMeronym, mer)
            for hom in request.form.getlist('homonyms[]'):
                add_unique_relation(word.id, WordHomonym, hom)
            for par in request.form.getlist('paronyms[]'):
                add_unique_relation(word.id, WordParonym, par)
            for area in request.form.getlist('usage_areas[]'):
                add_unique_relation(word.id, WordUsageArea, area, 'area')

            db.session.commit()

            # После добавления слова, пытаемся найти изображение по имени
            # Проверяем папку uploads на наличие файла с именем слова
            if not image_url:
                upload_path = os.path.join(current_app.root_path, UPLOAD_FOLDER)
                if os.path.exists(upload_path):
                    for ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
                        possible_filename = f"{word_text}.{ext}"
                        if os.path.exists(os.path.join(upload_path, possible_filename)):
                            word.image_url = f"/{UPLOAD_FOLDER}{possible_filename}"
                            db.session.commit()
                            flash(f'✅ Rasm "{possible_filename}" avtomatik bog\'landi!', 'success')
                            break

            flash(f'✅ So\'z "{word_text}" muvaffaqiyatli qo\'shildi!', 'success')
            return redirect(url_for('admin.words'))

        except Exception as e:
            db.session.rollback()
            flash(f'❌ Xatolik yuz berdi: {str(e)}', 'danger')
            print(f"Error adding word: {e}")
            return redirect(url_for('admin.add_word'))

    return render_template('admin/word_form.html')


@admin_bp.route('/words/edit/<int:word_id>', methods=['GET', 'POST'])
@admin_required
def edit_word(word_id):
    word = Word.query.get_or_404(word_id)

    if request.method == 'POST':
        # Обновляем основные поля
        word.word = request.form.get('word', '').strip().lower()
        word.definition = request.form.get('definition', '')
        word.etymology = request.form.get('etymology', '')
        word.translation_en = request.form.get('translation_en', '').strip()
        word.definition_en = request.form.get('definition_en', '').strip()
        word.example_uz = request.form.get('example_uz', '').strip()
        word.example_en = request.form.get('example_en', '').strip()
        word.pronunciation = request.form.get('pronunciation', '').strip()
        word.part_of_speech_en = request.form.get('part_of_speech_en', '').strip()
        word.etymology_en = request.form.get('etymology_en', '').strip()

        # Обработка изображения
        image_url = request.form.get('image_url', '').strip()
        image_file = request.files.get('image_file')
        remove_image_flag = request.form.get('remove_image', 'false') == 'true'

        # Если нужно удалить изображение
        if remove_image_flag and word.image_url:
            delete_image(word.image_url)
            word.image_url = None
            flash('Rasm o\'chirildi', 'info')

        # Если загружен новый файл
        if image_file and allowed_file(image_file.filename):
            # Удаляем старое изображение если есть
            if word.image_url:
                delete_image(word.image_url)
            saved_url = save_image(image_file, word.word)
            if saved_url:
                image_url = saved_url
                flash('Rasm muvaffaqiyatli yangilandi!', 'success')
            else:
                flash('Rasm yuklashda xatolik yuz berdi', 'danger')

        # Если URL введен вручную
        if image_url and not image_file:
            if word.image_url and word.image_url != image_url and word.image_url.startswith('/static/uploads/'):
                delete_image(word.image_url)

        word.image_url = image_url if image_url else None

        # Очищаем старые связи
        WordCategory.query.filter_by(word_id=word.id).delete()
        WordSynonym.query.filter_by(word_id=word.id).delete()
        WordAntonym.query.filter_by(word_id=word.id).delete()
        WordHyperonym.query.filter_by(word_id=word.id).delete()
        WordHyponym.query.filter_by(word_id=word.id).delete()
        WordHolonym.query.filter_by(word_id=word.id).delete()
        WordMeronym.query.filter_by(word_id=word.id).delete()
        WordHomonym.query.filter_by(word_id=word.id).delete()
        WordParonym.query.filter_by(word_id=word.id).delete()
        WordUsageArea.query.filter_by(word_id=word.id).delete()

        # Добавляем новые связи
        add_unique_categories(word.id, request.form.getlist('categories[]'))
        for syn in request.form.getlist('synonyms[]'):
            add_unique_relation(word.id, WordSynonym, syn)
        for ant in request.form.getlist('antonyms[]'):
            add_unique_relation(word.id, WordAntonym, ant)
        for hyp in request.form.getlist('hyperonyms[]'):
            add_unique_relation(word.id, WordHyperonym, hyp)
        for hypo in request.form.getlist('hyponyms[]'):
            add_unique_relation(word.id, WordHyponym, hypo)
        for hol in request.form.getlist('holonyms[]'):
            add_unique_relation(word.id, WordHolonym, hol)
        for mer in request.form.getlist('meronyms[]'):
            add_unique_relation(word.id, WordMeronym, mer)
        for hom in request.form.getlist('homonyms[]'):
            add_unique_relation(word.id, WordHomonym, hom)
        for par in request.form.getlist('paronyms[]'):
            add_unique_relation(word.id, WordParonym, par)
        for area in request.form.getlist('usage_areas[]'):
            add_unique_relation(word.id, WordUsageArea, area, 'area')

        db.session.commit()
        flash(f'So\'z "{word.word}" muvaffaqiyatli yangilandi', 'success')
        return redirect(url_for('admin.words'))

    word_data = {
        'id': word.id,
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
    }
    return render_template('admin/word_form.html', word=word_data)


@admin_bp.route('/words/delete/<int:word_id>')
@admin_required
def delete_word(word_id):
    word = Word.query.get_or_404(word_id)
    word_text = word.word

    # Удаляем изображение если оно есть
    if word.image_url:
        delete_image(word.image_url)

    db.session.delete(word)
    db.session.commit()
    flash(f'So\'z "{word_text}" o\'chirildi', 'success')
    return redirect(url_for('admin.words'))


# ========== УПРАВЛЕНИЕ КАТЕГОРИЯМИ ==========
@admin_bp.route('/categories')
@admin_required
def categories():
    cats = db.session.query(WordCategory.category).distinct().order_by(WordCategory.category).all()
    categories = [cat[0] for cat in cats]
    category_words_count = {}
    categories_with_words = 0
    for category in categories:
        count = WordCategory.query.filter_by(category=category).count()
        category_words_count[category] = count
        if count > 0:
            categories_with_words += 1
    return render_template('admin/categories.html',
                           categories=categories,
                           category_words_count=category_words_count,
                           categories_with_words=categories_with_words)


@admin_bp.route('/categories/add', methods=['POST'])
@admin_required
def add_category():
    category_name = request.form.get('category_name', '').strip().lower()
    if not category_name:
        flash('Kategoriya nomi kiritilishi shart', 'danger')
        return redirect(url_for('admin.categories'))

    existing = db.session.query(WordCategory).filter_by(category=category_name).first()
    if existing:
        flash(f'"{category_name}" kategoriyasi allaqachon mavjud', 'danger')
        return redirect(url_for('admin.categories'))

    test_word = Word(
        word=f"_category_placeholder_{category_name}",
        definition="Xizmat ko'rsatish uchun yozuv"
    )
    db.session.add(test_word)
    db.session.flush()
    db.session.add(WordCategory(word_id=test_word.id, category=category_name))
    db.session.commit()

    flash(f'"{category_name}" kategoriyasi muvaffaqiyatli qo\'shildi', 'success')
    return redirect(url_for('admin.categories'))


@admin_bp.route('/categories/edit/<path:category>', methods=['GET', 'POST'])
@admin_required
def edit_category(category):
    if request.method == 'POST':
        new_name = request.form.get('category_name', '').strip().lower()
        if not new_name:
            flash('Kategoriya nomi kiritilishi shart', 'danger')
            return redirect(url_for('admin.categories'))
        if category == new_name:
            flash('Kategoriya nomi o\'zgarmadi', 'info')
            return redirect(url_for('admin.categories'))

        existing = WordCategory.query.filter_by(category=new_name).first()
        if existing:
            flash(f'"{new_name}" kategoriyasi allaqachon mavjud', 'danger')
            return redirect(url_for('admin.categories'))

        categories = WordCategory.query.filter_by(category=category).all()
        if categories:
            for cat in categories:
                cat.category = new_name
            db.session.commit()
            flash(f'"{category}" -> "{new_name}" muvaffaqiyatli yangilandi', 'success')
        else:
            flash(f'"{category}" kategoriyasi topilmadi', 'danger')
        return redirect(url_for('admin.categories'))

    return render_template('admin/edit_category.html', category=category)


@admin_bp.route('/categories/delete/<path:category>')
@admin_required
def delete_category(category):
    words_with_category = WordCategory.query.filter_by(category=category).all()
    if words_with_category:
        real_words = []
        placeholder_ids = []
        for cat in words_with_category:
            word = Word.query.get(cat.word_id)
            if word:
                if word.word.startswith('_category_placeholder_'):
                    placeholder_ids.append(cat.id)
                else:
                    real_words.append(word.word)
        if real_words:
            flash(
                f'"{category}" kategoriyasida so\'zlar bor: {", ".join(real_words[:3])}. Avval ularni o\'chiring yoki boshqa kategoriyaga o\'tkazing.',
                'danger')
        elif placeholder_ids:
            WordCategory.query.filter(WordCategory.id.in_(placeholder_ids)).delete(synchronize_session=False)
            Word.query.filter(Word.word.like('_category_placeholder_%')).delete(synchronize_session=False)
            db.session.commit()
            flash(f'"{category}" kategoriyasi o\'chirildi', 'success')
    else:
        flash(f'"{category}" kategoriyasi topilmadi', 'danger')
    return redirect(url_for('admin.categories'))


# ========== IMPORT / EXPORT ==========
@admin_bp.route('/import-export')
@admin_required
def import_export():
    return render_template('admin/import_export.html')


@admin_bp.route('/api/export-json')
@admin_required
def export_json():
    words = Word.query.all()
    data = []
    for word in words:
        if word.word.startswith('_category_placeholder_'):
            continue
        word_data = {
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
            'paronyms': [par.related_word for par in word.paronyms if
                         par.related_word and par.related_word.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '']],
            'usage_areas': [area.area for area in word.usage_areas]
        }
        data.append(word_data)

    response = jsonify(data)
    response.headers['Content-Disposition'] = 'attachment; filename=gardening_export.json'
    response.headers['Content-Type'] = 'application/json'
    return response


@admin_bp.route('/api/import-json', methods=['POST'])
@admin_required
def import_json():
    import json

    if 'file' not in request.files:
        flash('Fayl tanlanmagan', 'danger')
        return redirect(url_for('admin.import_export'))

    file = request.files['file']
    if file.filename == '':
        flash('Fayl tanlanmagan', 'danger')
        return redirect(url_for('admin.import_export'))

    if not file.filename.endswith('.json'):
        flash('Faqat JSON fayllar qabul qilinadi', 'danger')
        return redirect(url_for('admin.import_export'))

    try:
        content = file.read().decode('utf-8')
        data = json.loads(content)

        clear_existing = request.form.get('clear_existing') == 'on'
        if clear_existing:
            # Удаляем все изображения перед очисткой
            words_to_delete = Word.query.filter(Word.word.notlike('_category_placeholder_%')).all()
            for w in words_to_delete:
                if w.image_url:
                    delete_image(w.image_url)
            Word.query.filter(Word.word.notlike('_category_placeholder_%')).delete()
            db.session.commit()
            flash('Mavjud ma\'lumotlar tozalandi', 'info')

        imported_count = 0
        duplicate_in_json = 0
        errors = []
        temp_words = set()

        for idx, item in enumerate(data):
            word_text = None
            for key in ['uzbek', 'word', 'Qishloq xo\'jaligi terminlari', 'soz', 'name']:
                if key in item and item[key]:
                    word_text = str(item[key]).strip().lower()
                    break

            if not word_text:
                continue

            if word_text in temp_words:
                duplicate_in_json += 1
            temp_words.add(word_text)

            try:
                definition = item.get('Izohi', '') or item.get('определение', '') or item.get('definition',
                                                                                              '') or item.get(
                    'definition_uz', '')
                if not definition:
                    definition = "Ta'rif mavjud emas"

                etymology = item.get('Etimologiyasi', '') or item.get('etymology_uz', '')
                if isinstance(etymology, list):
                    etymology = ' '.join(etymology)

                translation_en = item.get('Tarjimasi (ingliz tili)', '') or item.get('english', '')
                if translation_en and isinstance(translation_en, str):
                    translation_en = translation_en.strip()

                definition_en = item.get('definition_en', '')
                example_uz = item.get('example_uz', '')
                example_en = item.get('example_en', '')
                pronunciation = item.get('pronunciation', '')
                part_of_speech_en = item.get('part_of_speech_en', '')
                etymology_en = item.get('etymology_en', '')
                image_url = item.get('image_url', '')

                word = Word(
                    word=word_text,
                    definition=definition,
                    etymology=etymology,
                    translation_en=translation_en,
                    definition_en=definition_en,
                    example_uz=example_uz,
                    example_en=example_en,
                    pronunciation=pronunciation,
                    part_of_speech_en=part_of_speech_en,
                    etymology_en=etymology_en,
                    image_url=image_url
                )
                db.session.add(word)
                db.session.flush()

                turkum = item.get('turkumi', '') or item.get('part_of_speech_uz', '')
                if turkum:
                    added_cats = set()
                    for cat in str(turkum).split(','):
                        cat = cat.strip()
                        if cat and cat not in added_cats:
                            added_cats.add(cat)
                            if not WordCategory.query.filter_by(word_id=word.id, category=cat).first():
                                db.session.add(WordCategory(word_id=word.id, category=cat))

                sinonim = item.get('sinonimi (ma\'nodoshi)', '') or item.get('sinonimi', '') or item.get('synonyms_uz',
                                                                                                         '')
                if sinonim:
                    added_syns = set()
                    for syn in str(sinonim).split(','):
                        syn = syn.strip()
                        if syn and syn.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-', '—']:
                            if syn not in added_syns:
                                added_syns.add(syn)
                                if not WordSynonym.query.filter_by(word_id=word.id, related_word=syn).first():
                                    db.session.add(WordSynonym(word_id=word.id, related_word=syn))

                antonim = item.get('antonimi (zid ma\'nosi)', '') or item.get('antonimi', '') or item.get('antonyms_uz',
                                                                                                          '')
                if antonim:
                    added_ants = set()
                    for ant in str(antonim).split(','):
                        ant = ant.strip()
                        if ant and ant.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-', '—']:
                            if ant not in added_ants:
                                added_ants.add(ant)
                                if not WordAntonym.query.filter_by(word_id=word.id, related_word=ant).first():
                                    db.session.add(WordAntonym(word_id=word.id, related_word=ant))

                giperonim = item.get('giperonimi (jins)', '') or item.get('giperonimi', '') or item.get('гиперонимы',
                                                                                                        '') or item.get(
                    'hyperonyms', '')
                if giperonim:
                    added_hyps = set()
                    for hyp in str(giperonim).split(','):
                        hyp = hyp.strip()
                        if hyp and hyp.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '']:
                            if hyp not in added_hyps:
                                added_hyps.add(hyp)
                                if not WordHyperonym.query.filter_by(word_id=word.id, related_word=hyp).first():
                                    db.session.add(WordHyperonym(word_id=word.id, related_word=hyp))

                giponim = item.get('giponimi (tur)', '') or item.get('giponimi', '') or item.get('гипонимы',
                                                                                                 '') or item.get(
                    'hyponyms', '')
                if giponim:
                    added_hypos = set()
                    for hypo in str(giponim).split(','):
                        hypo = hypo.strip()
                        if hypo and hypo.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '']:
                            if hypo not in added_hypos:
                                added_hypos.add(hypo)
                                if not WordHyponym.query.filter_by(word_id=word.id, related_word=hypo).first():
                                    db.session.add(WordHyponym(word_id=word.id, related_word=hypo))

                xolonim = item.get('xolonim (butun)i', '') or item.get('xolonim', '') or item.get('holonyms', '')
                if xolonim:
                    added_hols = set()
                    for hol in str(xolonim).split(','):
                        hol = hol.strip()
                        if hol and hol.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '']:
                            if hol not in added_hols:
                                added_hols.add(hol)
                                if not WordHolonym.query.filter_by(word_id=word.id, related_word=hol).first():
                                    db.session.add(WordHolonym(word_id=word.id, related_word=hol))

                meronim = item.get('meronimi (qismi)', '') or item.get('meronim', '') or item.get('meronyms', '')
                if meronim:
                    added_mers = set()
                    for mer in str(meronim).split(','):
                        mer = mer.strip()
                        if mer and mer.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '']:
                            if mer not in added_mers:
                                added_mers.add(mer)
                                if not WordMeronym.query.filter_by(word_id=word.id, related_word=mer).first():
                                    db.session.add(WordMeronym(word_id=word.id, related_word=mer))

                omonim = item.get('omonimi (shakldoshi)', '') or item.get('omonim', '') or item.get('homonyms', '')
                if omonim and omonim not in [None, 'null', 'None', '']:
                    added_homs = set()
                    for hom in str(omonim).split(','):
                        hom = hom.strip()
                        if hom and hom.lower() not in ['yo\'q', 'yoq', 'нет', 'none', 'null', '']:
                            if hom not in added_homs:
                                added_homs.add(hom)
                                if not WordHomonym.query.filter_by(word_id=word.id, related_word=hom).first():
                                    db.session.add(WordHomonym(word_id=word.id, related_word=hom))

                paronim = item.get('paronimi (talaffuzdoshi)', '') or item.get('paronim', '') or item.get('paronyms',
                                                                                                          '')
                if paronim and paronim not in [None, 'null', 'None', '']:
                    added_pars = set()
                    for par in str(paronim).split(','):
                        par = par.strip()
                        if par and par.lower() not in ['yo\'q', 'yoq', 'нет', 'none', 'null', '']:
                            if par not in added_pars:
                                added_pars.add(par)
                                if not WordParonym.query.filter_by(word_id=word.id, related_word=par).first():
                                    db.session.add(WordParonym(word_id=word.id, related_word=par))

                usage_uz = item.get('qaysi sohada qo\'llanilishi', '') or item.get('qaysi sohada qollanilishi',
                                                                                   '') or item.get('qollanilishi',
                                                                                                   '') or item.get(
                    'field_uz', '')
                usage_en = item.get('field_en', '')

                all_usage = []
                if usage_uz:
                    for area in str(usage_uz).split(','):
                        area = area.strip()
                        if area and area.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-', '—', 'null']:
                            all_usage.append(area)
                if usage_en:
                    for area in str(usage_en).split(','):
                        area = area.strip()
                        if area and area.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-', '—', 'null']:
                            all_usage.append(area)

                for area in all_usage:
                    if not WordUsageArea.query.filter_by(word_id=word.id, area=area).first():
                        db.session.add(WordUsageArea(word_id=word.id, area=area))

                synonyms_en = item.get('synonyms_en', '')
                if synonyms_en:
                    for syn_en in str(synonyms_en).split(','):
                        syn_en = syn_en.strip()
                        if syn_en and syn_en.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '']:
                            if not WordSynonym.query.filter_by(word_id=word.id, related_word=syn_en).first():
                                db.session.add(WordSynonym(word_id=word.id, related_word=syn_en))

                imported_count += 1

                if imported_count % 100 == 0:
                    db.session.commit()
                    print(f"✅ {imported_count} ta so'z import qilindi...")

            except Exception as e:
                errors.append(f"'{word_text}': {str(e)}")
                print(f"❌ ERROR for '{word_text}': {str(e)}")
                continue

        db.session.commit()

        # После импорта автоматически привязываем изображения
        linked, skipped = auto_link_images()
        if linked > 0:
            flash(f'✅ {linked} ta rasm avtomatik bog\'landi!', 'success')
        if skipped > 0:
            flash(f'ℹ️ {skipped} ta rasm allaqachon bog\'langan yoki mos kelmadi', 'info')

        total_records = Word.query.filter(Word.word.notlike('_category_placeholder_%')).count()
        unique_words = db.session.query(Word.word).distinct().filter(
            Word.word.notlike('_category_placeholder_%')).count()
        total_usage = WordUsageArea.query.count()

        msg = f'✅ Jami: {len(data)} ta yozuv (JSON da)\n'
        msg += f'✅ Import qilindi: {imported_count} ta yozuv\n'
        msg += f'⚠️ JSON da dublikatlar: {duplicate_in_json} ta\n'
        msg += f'📊 Jami yozuvlar bazada: {total_records} ta\n'
        msg += f'🔍 Unikal so\'zlar: {unique_words} ta\n'
        msg += f'🏷️ Qo\'llanilish sohalari: {total_usage} ta yozuv'

        if errors:
            msg += f'\n❌ Xatolar: {len(errors)} ta'

        flash(msg, 'success')

    except json.JSONDecodeError as e:
        flash(f'JSON fayl xatosi: {str(e)}', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Import xatosi: {str(e)}', 'danger')
        print(f"❌ Import exception: {str(e)}")

    return redirect(url_for('admin.import_export'))


# ========== API ДЛЯ ПОИСКА СЛОВ ==========
@admin_bp.route('/api/words/search')
def api_words_search():
    query = request.args.get('q', '').lower()
    if len(query) < 2:
        return jsonify([])
    words = Word.query.filter(
        Word.word.like(f'%{query}%'),
        ~Word.word.startswith('_category_placeholder_')
    ).limit(10).all()
    return jsonify([word.word for word in words])


# ========== СОЗДАНИЕ АДМИНИСТРАТОРА ==========
def create_admin():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print('✅ Admin created: username=admin, password=admin123')
    else:
        print('✅ Admin already exists')


# ========== РЕДАКТИРОВАНИЕ КАТЕГОРИИ ЧЕРЕЗ AJAX ==========
@admin_bp.route('/categories/edit-ajax', methods=['POST'])
@admin_required
def edit_category_ajax():
    old_name = request.form.get('old_name', '').strip().lower()
    new_name = request.form.get('category_name', '').strip().lower()

    if not new_name:
        flash('Kategoriya nomi kiritilishi shart', 'danger')
        return redirect(url_for('admin.categories'))

    if old_name == new_name:
        flash('Kategoriya nomi o\'zgarmadi', 'info')
        return redirect(url_for('admin.categories'))

    existing = WordCategory.query.filter_by(category=new_name).first()
    if existing and old_name != new_name:
        flash(f'"{new_name}" kategoriyasi allaqachon mavjud', 'danger')
        return redirect(url_for('admin.categories'))

    categories = WordCategory.query.filter_by(category=old_name).all()
    if categories:
        for cat in categories:
            cat.category = new_name
        db.session.commit()
        flash(f'"{old_name}" -> "{new_name}" muvaffaqiyatli yangilandi', 'success')
    else:
        flash(f'"{old_name}" kategoriyasi topilmadi', 'danger')

    return redirect(url_for('admin.categories'))