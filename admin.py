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
from data_sync import load_blob_map, find_image_url

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ========== НАСТРОЙКИ ДЛЯ ЗАГРУЗКИ ФАЙЛОВ ==========
UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}


def allowed_file(filename):
    """Проверяет разрешено ли расширение файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file, custom_name=None):
    """Save an uploaded image to Vercel Blob when configured, otherwise locally."""
    if not file or not allowed_file(file.filename):
        return None

    ext = file.filename.rsplit('.', 1)[1].lower()
    base = secure_filename(custom_name or os.path.splitext(file.filename)[0]) or uuid.uuid4().hex
    filename = f"{base}.{ext}"

    token = os.environ.get('BLOB_READ_WRITE_TOKEN')
    if token:
        try:
            try:
                import vercel_blob.blob_store as vb_store
            except Exception:
                import vercel_blob as vb_store
            payload = file.read()
            # The package reads BLOB_READ_WRITE_TOKEN from the environment.
            # Keep a stable pathname so the image can be matched to the term.
            result = vb_store.put(filename, payload, {'addRandomSuffix': 'false'})
            if hasattr(result, 'url'):
                return result.url
            if isinstance(result, dict):
                return result.get('url')
        except Exception as exc:
            current_app.logger.exception('Vercel Blob upload failed: %s', exc)
            try:
                file.stream.seek(0)
            except Exception:
                pass

    upload_path = os.path.join(current_app.root_path, UPLOAD_FOLDER)
    os.makedirs(upload_path, exist_ok=True)
    filepath = os.path.join(upload_path, filename)
    file.save(filepath)
    return f"/{UPLOAD_FOLDER}{filename}"


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
@admin_bp.route('/dashboard')
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
    blob_map = load_blob_map(current_app.root_path, app=current_app)
    if request.method == 'POST':
        linked = 0
        skipped = 0
        for word in Word.query.filter(~Word.word.startswith('_category_placeholder_')).all():
            url = find_image_url(word.word, blob_map)
            if url:
                # Replace stale/guessed URLs as well as empty values.
                if word.image_url != url:
                    word.image_url = url
                    linked += 1
                else:
                    skipped += 1
            else:
                skipped += 1
        if linked:
            db.session.commit()
        flash(f'✅ {linked} ta rasm muvaffaqiyatli bog\'landi!', 'success')
        if skipped:
            flash(f'ℹ️ {skipped} ta yozuv allaqachon bog\'langan yoki Blob fayli topilmadi', 'info')
        return redirect(url_for('admin.dashboard'))

    images = []
    for key, url in list(blob_map.items())[:5000]:
        word = Word.query.filter(Word.word.ilike(key)).first()
        images.append({
            'filename': url.rsplit('/', 1)[-1],
            'word': key,
            'found_word': word.word if word else None,
            'has_image': bool(word and word.image_url),
            'url': url,
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

        existing = Word.query.filter(db.func.lower(Word.word) == word_text.lower()).first()
        if existing:
            flash(f'Bu so\'z allaqachon mavjud: "{existing.word}"', 'warning')
            return redirect(url_for('admin.edit_word', word_id=existing.id))

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
    """
    Надёжный импорт JSON.

    Режимы:
    - с галочкой clear_existing: полностью заменяет словарную БД содержимым JSON;
    - без галочки: обновляет существующие слова и добавляет новые;
    - дубликаты внутри одного JSON не создаются;
    - связанные таблицы очищаются безопасно;
    - изображения в static/uploads физически НЕ удаляются.
    """
    import json

    if 'file' not in request.files:
        flash('Fayl tanlanmagan', 'danger')
        return redirect(url_for('admin.import_export'))

    file = request.files['file']
    if not file or file.filename == '':
        flash('Fayl tanlanmagan', 'danger')
        return redirect(url_for('admin.import_export'))

    if not file.filename.lower().endswith('.json'):
        flash('Faqat JSON fayllar qabul qilinadi', 'danger')
        return redirect(url_for('admin.import_export'))

    def first_value(item, keys, default=''):
        """Возвращает первое непустое значение из набора ключей."""
        for key in keys:
            value = item.get(key)
            if value is not None and value != '':
                return value
        return default

    def as_list(value):
        """Нормализует строку/список в список непустых значений."""
        if value is None:
            return []

        if isinstance(value, (list, tuple, set)):
            raw = list(value)
        else:
            value = str(value).strip()
            if not value:
                return []
            # Большинство полей в исходном JSON разделены запятыми.
            raw = value.split(',')

        ignored = {
            '', '-', '—', 'yo‘q', "yo'q", 'yoq',
            'нет', 'none', 'null', 'None'
        }

        result = []
        seen = set()

        for item_value in raw:
            item_value = str(item_value).strip()
            if not item_value or item_value in ignored or item_value.lower() in {
                '', '-', '—', "yo'q", 'yoq', 'нет', 'none', 'null'
            }:
                continue

            marker = item_value.casefold()
            if marker not in seen:
                seen.add(marker)
                result.append(item_value)

        return result

    def replace_relations(word, item):
        """Полностью заменяет связи одного слова данными из JSON."""
        WordCategory.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordSynonym.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordAntonym.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordHyperonym.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordHyponym.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordHolonym.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordMeronym.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordHomonym.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordParonym.query.filter_by(word_id=word.id).delete(synchronize_session=False)
        WordUsageArea.query.filter_by(word_id=word.id).delete(synchronize_session=False)

        # Категории / часть речи
        categories_value = first_value(
            item,
            ['categories', 'turkumi', 'part_of_speech_uz'],
            []
        )
        for category in as_list(categories_value):
            db.session.add(WordCategory(word_id=word.id, category=category))

        # Синонимы: поддерживаем и экспортный формат, и yangi.json
        synonyms_value = first_value(
            item,
            ["synonyms", "sinonimi (ma'nodoshi)", 'sinonimi', 'synonyms_uz'],
            []
        )
        for value in as_list(synonyms_value):
            db.session.add(WordSynonym(word_id=word.id, related_word=value))

        # Английские синонимы также сохраняем в существующую таблицу
        for value in as_list(item.get('synonyms_en', [])):
            exists = WordSynonym.query.filter_by(
                word_id=word.id,
                related_word=value
            ).first()
            if not exists:
                db.session.add(WordSynonym(word_id=word.id, related_word=value))

        relation_specs = [
            (
                WordAntonym,
                ['antonyms', "antonimi (zid ma'nosi)", 'antonimi', 'antonyms_uz']
            ),
            (
                WordHyperonym,
                ['hyperonyms', 'гиперонимы', 'giperonimi (jins)', 'giperonimi']
            ),
            (
                WordHyponym,
                ['hyponyms', 'гипонимы', 'giponimi (tur)', 'giponimi']
            ),
            (
                WordHolonym,
                ['holonyms', 'xolonim (butun)i', 'xolonim']
            ),
            (
                WordMeronym,
                ['meronyms', 'meronimi (qismi)', 'meronim']
            ),
            (
                WordHomonym,
                ['homonyms', 'omonimi (shakldoshi)', 'omonim']
            ),
            (
                WordParonym,
                ['paronyms', 'paronimi (talaffuzdoshi)', 'paronim']
            ),
        ]

        for model, keys in relation_specs:
            values = as_list(first_value(item, keys, []))
            for value in values:
                db.session.add(model(word_id=word.id, related_word=value))

        # Области применения: экспортный и исходный форматы
        usage_values = []

        for key in [
            'usage_areas',
            "qaysi sohada qo'llanilishi",
            'qaysi sohada qollanilishi',
            'qollanilishi',
            'field_uz',
            'field_en',
        ]:
            usage_values.extend(as_list(item.get(key, [])))

        seen_usage = set()
        for area in usage_values:
            marker = area.casefold()
            if marker in seen_usage:
                continue
            seen_usage.add(marker)
            db.session.add(WordUsageArea(word_id=word.id, area=area))

    def clear_dictionary_tables():
        """
        Полностью очищает словарные таблицы.

        Таблица User НЕ удаляется, поэтому администратор остаётся.
        Файлы static/uploads НЕ удаляются.
        """
        WordCategory.query.delete(synchronize_session=False)
        WordSynonym.query.delete(synchronize_session=False)
        WordAntonym.query.delete(synchronize_session=False)
        WordHyperonym.query.delete(synchronize_session=False)
        WordHyponym.query.delete(synchronize_session=False)
        WordHolonym.query.delete(synchronize_session=False)
        WordMeronym.query.delete(synchronize_session=False)
        WordHomonym.query.delete(synchronize_session=False)
        WordParonym.query.delete(synchronize_session=False)
        WordUsageArea.query.delete(synchronize_session=False)
        Word.query.delete(synchronize_session=False)
        db.session.flush()

    try:
        # utf-8-sig также корректно читает JSON с BOM.
        content = file.read().decode('utf-8-sig')
        data = json.loads(content)

        if not isinstance(data, list):
            flash('JSON ildiz elementi ro‘yxat (array) bo‘lishi kerak', 'danger')
            return redirect(url_for('admin.import_export'))

        clear_existing = request.form.get('clear_existing') == 'on'

        if clear_existing:
            try:
                clear_dictionary_tables()
                db.session.commit()
                flash(
                    '✅ Eski terminlar va barcha bog‘lanishlar to‘liq o‘chirildi.',
                    'success'
                )
            except Exception as exc:
                db.session.rollback()
                flash(
                    f'❌ Eski ma’lumotlarni o‘chirishda xatolik: {exc}',
                    'danger'
                )
                return redirect(url_for('admin.import_export'))

        imported_count = 0
        created_count = 0
        updated_count = 0
        duplicate_in_json = 0
        skipped_count = 0
        errors = []
        seen_json_words = set()

        # Локальные изображения используются как fallback.
        # Если Blob доступен, load_blob_map также может вернуть Blob URL.
        try:
            image_map = load_blob_map(current_app.root_path, app=current_app)
        except Exception as exc:
            current_app.logger.warning('Image map load failed during import: %s', exc)
            image_map = {}

        for idx, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                skipped_count += 1
                continue

            word_text = first_value(
                item,
                ['uzbek', 'word', "Qishloq xo'jaligi terminlari", 'soz', 'name'],
                ''
            )
            word_text = str(word_text).strip()

            if not word_text:
                skipped_count += 1
                continue

            word_key = word_text.casefold()

            # Не импортируем одно и то же слово дважды из одного JSON.
            if word_key in seen_json_words:
                duplicate_in_json += 1
                continue
            seen_json_words.add(word_key)

            try:
                definition = first_value(
                    item,
                    ['Izohi', 'определение', 'definition', 'definition_uz'],
                    "Ta'rif mavjud emas"
                )
                if not definition:
                    definition = "Ta'rif mavjud emas"

                etymology = first_value(
                    item,
                    ['Etimologiyasi', 'etymology', 'etymology_uz'],
                    ''
                )
                if isinstance(etymology, list):
                    etymology = ' '.join(str(v) for v in etymology)

                translation_en = first_value(
                    item,
                    ['Tarjimasi (ingliz tili)', 'translation_en', 'english'],
                    ''
                )

                definition_en = first_value(item, ['definition_en'], '')
                example_uz = first_value(item, ['example_uz'], '')
                example_en = first_value(item, ['example_en'], '')
                pronunciation = first_value(item, ['pronunciation'], '')
                part_of_speech_en = first_value(item, ['part_of_speech_en'], '')
                etymology_en = first_value(item, ['etymology_en'], '')

                incoming_image_url = str(item.get('image_url') or '').strip()

                # Case-insensitive upsert: повторно такое слово не создаём.
                word = Word.query.filter(
                    db.func.lower(Word.word) == word_text.lower()
                ).order_by(Word.id.asc()).first()

                if word is None:
                    word = Word(word=word_text, definition=str(definition))
                    db.session.add(word)
                    db.session.flush()
                    created_count += 1
                else:
                    updated_count += 1

                word.word = word_text
                word.definition = str(definition)
                word.etymology = str(etymology or '')
                word.translation_en = str(translation_en or '').strip()
                word.definition_en = str(definition_en or '')
                word.example_uz = str(example_uz or '')
                word.example_en = str(example_en or '')
                word.pronunciation = str(pronunciation or '')
                word.part_of_speech_en = str(part_of_speech_en or '')
                word.etymology_en = str(etymology_en or '')

                # Приоритет:
                # 1) image_url из JSON
                # 2) автосопоставление с Blob / static/uploads
                # 3) уже существующий image_url
                if incoming_image_url:
                    word.image_url = incoming_image_url
                else:
                    matched_url = find_image_url(word_text, image_map) if image_map else None
                    if matched_url:
                        word.image_url = matched_url

                replace_relations(word, item)

                imported_count += 1

                # На больших JSON сохраняем порциями.
                if imported_count % 100 == 0:
                    db.session.commit()
                    current_app.logger.info(
                        'JSON import progress: %s records',
                        imported_count
                    )

            except Exception as exc:
                db.session.rollback()
                errors.append(f'{word_text}: {exc}')
                current_app.logger.exception(
                    'JSON import error for %s',
                    word_text
                )
                # После rollback продолжаем со следующей записью.
                continue

        db.session.commit()

        # Дополнительная попытка привязать локальные изображения.
        # Она не создаёт термины и не влияет на их количество.
        try:
            linked, skipped_images = auto_link_images()
        except Exception as exc:
            current_app.logger.warning(
                'Auto-link after JSON import failed: %s',
                exc
            )
            linked, skipped_images = 0, 0

        total_records = Word.query.filter(
            ~Word.word.startswith('_category_placeholder_')
        ).count()

        unique_words = db.session.query(
            db.func.lower(Word.word)
        ).filter(
            ~Word.word.startswith('_category_placeholder_')
        ).distinct().count()

        total_usage = WordUsageArea.query.count()

        msg = (
            f'✅ JSON: {len(data)} ta yozuv\n'
            f'✅ Qayta ishlangan: {imported_count} ta\n'
            f'➕ Yangi: {created_count} ta\n'
            f'♻️ Yangilangan: {updated_count} ta\n'
            f'⚠️ JSON ichidagi dublikatlar: {duplicate_in_json} ta\n'
            f'⏭️ O‘tkazib yuborilgan: {skipped_count} ta\n'
            f'🖼️ Rasm bog‘landi: {linked} ta\n'
            f'📊 Bazadagi terminlar: {total_records} ta\n'
            f'🔍 Unikal terminlar: {unique_words} ta\n'
            f'🏷️ Qo‘llanilish sohasi yozuvlari: {total_usage} ta'
        )

        if errors:
            msg += f'\n❌ Xatolar: {len(errors)} ta'

        flash(msg, 'success' if not errors else 'warning')

    except json.JSONDecodeError as exc:
        db.session.rollback()
        flash(f'JSON fayl xatosi: {exc}', 'danger')

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('JSON import failed: %s', exc)
        flash(f'Import xatosi: {exc}', 'danger')

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
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    password = os.environ.get('ADMIN_PASSWORD')
    if not password:
        if os.environ.get('VERCEL'):
            current_app.logger.warning('ADMIN_PASSWORD is not set; admin account was not auto-created.')
            return None
        password = 'admin123'  # local development only
    admin = User.query.filter_by(username=username).first()
    if not admin:
        admin = User(
            username=username,
            password_hash=generate_password_hash(password),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        current_app.logger.info('Admin account created for %s', username)
    return admin


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