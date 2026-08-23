import json
import difflib
import os
import re
import unicodedata
from sqlalchemy import inspect, text

from models import (
    db, Word, WordCategory, WordSynonym, WordAntonym, WordHyperonym,
    WordHyponym, WordHolonym, WordMeronym, WordHomonym, WordParonym,
    WordUsageArea,
)


RELATION_MODELS = [
    WordCategory, WordSynonym, WordAntonym, WordHyperonym, WordHyponym,
    WordHolonym, WordMeronym, WordHomonym, WordParonym, WordUsageArea,
]


def normalize_key(value):
    value = unicodedata.normalize('NFKC', str(value or '')).lower().strip()
    for ch in ('’', '‘', '`', 'ʻ', 'ʼ', '´'):
        value = value.replace(ch, "'")
    value = re.sub(r'[-_]+', ' ', value)
    value = re.sub(r"[^\w\s']", ' ', value, flags=re.UNICODE)
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def term_variants(value):
    raw = str(value or '').strip()
    variants = [raw]
    no_parentheses = re.sub(r'\s*\([^)]*\)', '', raw).strip()
    if no_parentheses:
        variants.append(no_parentheses)
    if '(' in raw:
        variants.append(raw.split('(', 1)[0].strip())
    out = []
    for item in variants:
        key = normalize_key(item)
        if key and key not in out:
            out.append(key)
    return out


def split_values(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        source = value
    else:
        source = re.split(r'[,;]\s*', str(value))
    result = []
    for item in source:
        item = str(item).strip()
        if item and item.lower() not in {'-', '—', 'yoq', "yo'q", 'none', 'null', 'нет'}:
            if item not in result:
                result.append(item)
    return result


def _blob_name_variants(pathname):
    """Return conservative normalized keys for a Blob pathname.

    Vercel Blob may append a random suffix to uploaded filenames. We keep the
    exact filename stem and, when the final hyphenated part looks like a long
    random suffix, also expose the stem without that suffix.
    """
    from urllib.parse import unquote

    pathname = unquote(str(pathname or '')).strip()
    base = os.path.basename(pathname)
    stem = os.path.splitext(base)[0]
    raw_variants = [stem]

    # Typical public Blob URLs may use: Agrokimyo-AbCd1234....jpg
    stripped = re.sub(r'-[A-Za-z0-9]{8,}$', '', stem)
    if stripped and stripped != stem:
        raw_variants.append(stripped)

    result = []
    for raw in raw_variants:
        for variant in term_variants(raw):
            if variant and variant not in result:
                result.append(variant)
    return result


def _get_blob_store_module():
    """Return the Blob API module across vercel_blob package versions.

    Some releases expose list/put at ``vercel_blob.list`` while older releases
    expose them only as ``vercel_blob.blob_store.list``.  Using blob_store first
    keeps the project compatible with both local installs and Vercel builds.
    """
    try:
        import vercel_blob.blob_store as vb_store
        return vb_store
    except Exception:
        try:
            import vercel_blob
            return vercel_blob
        except Exception:
            return None


def load_vercel_blob_map(app=None):
    """Load real public image URLs from the connected Vercel Blob store."""
    token = os.environ.get('BLOB_READ_WRITE_TOKEN', '').strip()
    if not token:
        if app:
            app.logger.warning('BLOB_READ_WRITE_TOKEN is not set; Blob image sync skipped')
        return {}

    vb_store = _get_blob_store_module()
    if vb_store is None or not hasattr(vb_store, 'list'):
        if app:
            app.logger.warning('vercel_blob list API is unavailable in the installed package')
        return {}

    mapping = {}
    cursor = None
    page = 0

    try:
        while True:
            options = {'limit': '1000'}
            if cursor:
                options['cursor'] = cursor

            # The package reads BLOB_READ_WRITE_TOKEN from the environment.
            result = vb_store.list(options)
            if not isinstance(result, dict):
                if app:
                    app.logger.warning('Unexpected Vercel Blob list response: %r', type(result))
                break

            blobs = result.get('blobs', []) or []
            for blob in blobs:
                if not isinstance(blob, dict):
                    continue
                pathname = str(blob.get('pathname') or '')
                url = blob.get('url') or blob.get('downloadUrl')
                if not url:
                    continue
                if not pathname.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                    continue
                for key in _blob_name_variants(pathname):
                    mapping.setdefault(key, str(url))

            page += 1
            if not result.get('hasMore'):
                break
            cursor = result.get('cursor')
            if not cursor or page > 100:
                break

        if app:
            app.logger.info('Vercel Blob: loaded %s normalized image keys', len(mapping))
        return mapping

    except Exception as exc:
        if app:
            app.logger.exception('Could not list Vercel Blob images: %s', exc)
        return {}



def load_local_image_map(project_root, app=None):
    """Build term -> /static/uploads/... map from files shipped with the project.

    This is the offline/local fallback.  It lets PyCharm (and Vercel deployments
    that include ``static/uploads``) display images without any Blob token.
    Real live Vercel Blob URLs still have priority when a token is available.
    """
    from urllib.parse import quote

    upload_dir = os.path.join(project_root, 'static', 'uploads')
    if not os.path.isdir(upload_dir):
        if app:
            app.logger.info('Local image folder not found: %s', upload_dir)
        return {}

    allowed = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')
    mapping = {}
    files_seen = 0

    for filename in os.listdir(upload_dir):
        full_path = os.path.join(upload_dir, filename)
        if not os.path.isfile(full_path):
            continue
        if not filename.lower().endswith(allowed):
            continue

        files_seen += 1
        # quote only the filename; keep /static/uploads readable.
        local_url = '/static/uploads/' + quote(filename)
        stem = os.path.splitext(filename)[0]

        # Reuse the same conservative filename normalization as Blob objects.
        raw_variants = [stem]
        stripped = re.sub(r'-[A-Za-z0-9]{8,}$', '', stem)
        if stripped and stripped != stem:
            raw_variants.append(stripped)

        for raw in raw_variants:
            for key in term_variants(raw):
                mapping.setdefault(key, local_url)

    if app:
        app.logger.info(
            'Local images: found %s files, built %s normalized keys',
            files_seen, len(mapping)
        )
    return mapping

def load_blob_map(project_root, app=None):
    """Return normalized term -> image URL mapping.

    Priority:
      1. Real public URLs returned by the connected Vercel Blob API.
      2. Files physically present in ``static/uploads`` (local/PyCharm fallback).
      3. Legacy text URL files only when explicitly enabled.

    This means local development no longer requires BLOB_READ_WRITE_TOKEN just
    to display the 1085 JPG files already stored in ``static/uploads``.
    """
    remote_mapping = load_vercel_blob_map(app)
    if remote_mapping:
        return remote_mapping

    local_mapping = load_local_image_map(project_root, app=app)
    if local_mapping:
        return local_mapping

    if os.environ.get('ALLOW_BLOB_URL_FILE_FALLBACK', '0') != '1':
        return {}

    candidates = [
        os.path.join(project_root, 'blob_urls_correct.txt'),
        os.path.join(project_root, 'blob_urls.txt'),
    ]
    mapping = {}
    for path in candidates:
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' not in line:
                    continue
                key, url = line.split('=', 1)
                url = url.strip()
                if not url.startswith(('http://', 'https://')):
                    continue
                for variant in term_variants(key):
                    mapping.setdefault(variant, url)
        if mapping:
            break
    return mapping

def find_image_url(term, blob_map):
    variants = term_variants(term)
    for variant in variants:
        if variant in blob_map:
            return blob_map[variant]

    # Conservative typo/apostrophe fallback for filenames that differ only slightly
    # from the term in yangi.json. A high cutoff avoids linking unrelated pictures.
    keys = list(blob_map.keys())
    for variant in variants:
        if len(variant) < 7:
            continue
        matches = difflib.get_close_matches(variant, keys, n=1, cutoff=0.94)
        if matches:
            candidate = matches[0]
            if abs(len(candidate) - len(variant)) <= 4:
                return blob_map[candidate]
    return None


def _ensure_meta_table():
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS app_meta ('
        'key VARCHAR(100) PRIMARY KEY, value VARCHAR(255))'
    ))
    db.session.commit()


def _get_meta(key):
    row = db.session.execute(
        text('SELECT value FROM app_meta WHERE key=:key'), {'key': key}
    ).first()
    return row[0] if row else None


def _set_meta(key, value):
    if _get_meta(key) is None:
        db.session.execute(
            text('INSERT INTO app_meta (key, value) VALUES (:key, :value)'),
            {'key': key, 'value': value}
        )
    else:
        db.session.execute(
            text('UPDATE app_meta SET value=:value WHERE key=:key'),
            {'key': key, 'value': value}
        )
    db.session.commit()


def ensure_word_columns():
    """Adds fields used by the current model to an older deployed database."""
    inspector = inspect(db.engine)
    if 'word' not in inspector.get_table_names():
        return
    existing = {col['name'] for col in inspector.get_columns('word')}
    additions = {
        'definition_en': 'TEXT',
        'example_uz': 'TEXT',
        'example_en': 'TEXT',
        'pronunciation': 'VARCHAR(100)',
        'part_of_speech_en': 'VARCHAR(50)',
        'etymology_en': 'TEXT',
        'image_url': 'VARCHAR(500)',
        'created_at': 'TIMESTAMP',
        'updated_at': 'TIMESTAMP',
    }
    changed = False
    for column, sql_type in additions.items():
        if column not in existing:
            db.session.execute(text(f'ALTER TABLE word ADD COLUMN {column} {sql_type}'))
            changed = True
    if changed:
        db.session.commit()


def _replace_relations(word, model, field_name, values, attr='related_word'):
    model.query.filter_by(word_id=word.id).delete(synchronize_session=False)
    seen = set()
    for value in values:
        clean = str(value).strip()
        if not clean:
            continue
        marker = normalize_key(clean)
        if marker in seen:
            continue
        seen.add(marker)
        if model is WordCategory:
            db.session.add(model(word_id=word.id, category=clean))
        elif model is WordUsageArea:
            db.session.add(model(word_id=word.id, area=clean))
        else:
            db.session.add(model(word_id=word.id, **{attr: clean}))


def _looks_like_legacy_guessed_blob_url(url):
    """Detect the old fabricated URLs that never came from the Blob API."""
    value = str(url or '').strip().lower()
    return bool(re.match(r'^https://store_[^/]+\.blob\.vercel-storage\.com/', value))


def sync_blob_images(app, blob_map=None):
    """Refresh image_url values from the live Blob listing.

    Existing stale guessed URLs are replaced when a match exists.  If no match
    exists, only known legacy guessed URLs are cleared; legitimate external or
    local image URLs are preserved.
    """
    if blob_map is None:
        blob_map = load_blob_map(app.root_path, app=app)
    if not blob_map:
        return {'checked': 0, 'matched': 0, 'changed': 0, 'cleared_legacy': 0}

    checked = matched = changed = cleared_legacy = 0
    for word in Word.query.filter(~Word.word.startswith('_category_placeholder_')).all():
        checked += 1
        image_url = find_image_url(word.word, blob_map)
        if image_url:
            matched += 1
            if word.image_url != image_url:
                word.image_url = image_url
                changed += 1
        elif _looks_like_legacy_guessed_blob_url(word.image_url):
            word.image_url = None
            cleared_legacy += 1

        if checked % 200 == 0:
            db.session.commit()

    db.session.commit()
    return {
        'checked': checked,
        'matched': matched,
        'changed': changed,
        'cleared_legacy': cleared_legacy,
    }

def sync_dataset(app, force=False):
    project_root = app.root_path
    json_path = os.path.join(project_root, 'yangi.json')
    if not os.path.exists(json_path):
        app.logger.warning('yangi.json not found; dataset sync skipped')
        return {'synced': False, 'reason': 'missing_json'}

    _ensure_meta_table()
    dataset_version = app.config.get('DATASET_VERSION', 'unknown')
    previous_version = _get_meta('dataset_version')

    # Always refresh Blob URLs when a store is connected. This is intentionally
    # independent from DATASET_VERSION so a database previously synchronized
    # with guessed/broken URLs repairs itself on the next deployment.
    blob_map = load_blob_map(project_root, app=app)
    if not force and previous_version == dataset_version:
        blob_result = sync_blob_images(app, blob_map=blob_map)
        _set_meta('blob_matches', str(blob_result.get('matched', 0)))
        return {'synced': False, 'reason': 'already_current', 'blob_sync': blob_result}

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Existing rows indexed by normalized term. If old DB has duplicates, update the
    # first one and leave extra senses untouched rather than deleting user data.
    existing = {}
    for row in Word.query.all():
        existing.setdefault(normalize_key(row.word), row)

    created = 0
    updated = 0
    images = 0

    for index, item in enumerate(data, 1):
        term = str(item.get('uzbek') or item.get('word') or '').strip()
        if not term:
            continue
        key = normalize_key(term)
        word = existing.get(key)
        if word is None:
            word = Word(word=term, definition="Ta'rif mavjud emas")
            db.session.add(word)
            db.session.flush()
            existing[key] = word
            created += 1
        else:
            updated += 1

        word.word = term
        word.definition = item.get('definition_uz') or item.get('Izohi') or word.definition or "Ta'rif mavjud emas"
        word.etymology = item.get('etymology_uz') or item.get('Etimologiyasi') or ''
        word.translation_en = item.get('english') or item.get('Tarjimasi (ingliz tili)') or ''
        word.definition_en = item.get('definition_en') or ''
        word.example_uz = item.get('example_uz') or ''
        word.example_en = item.get('example_en') or ''
        word.pronunciation = item.get('pronunciation') or ''
        word.part_of_speech_en = item.get('part_of_speech_en') or ''
        word.etymology_en = item.get('etymology_en') or ''

        image_url = item.get('image_url') or find_image_url(term, blob_map)
        if image_url:
            word.image_url = image_url
            images += 1

        db.session.flush()
        _replace_relations(word, WordCategory, 'category', split_values(item.get('part_of_speech_uz') or item.get('turkumi')), attr='category')
        _replace_relations(word, WordSynonym, 'related_word', split_values(item.get('synonyms_uz')) + split_values(item.get('synonyms_en')))
        _replace_relations(word, WordAntonym, 'related_word', split_values(item.get('antonyms_uz') or item.get('antonimi')))
        _replace_relations(word, WordHyperonym, 'related_word', split_values(item.get('hyperonyms') or item.get('giperonimi')))
        _replace_relations(word, WordHyponym, 'related_word', split_values(item.get('hyponyms') or item.get('giponimi')))
        _replace_relations(word, WordHolonym, 'related_word', split_values(item.get('holonyms') or item.get('xolonim')))
        _replace_relations(word, WordMeronym, 'related_word', split_values(item.get('meronyms') or item.get('meronim')))
        _replace_relations(word, WordHomonym, 'related_word', split_values(item.get('homonyms') or item.get('omonim')))
        _replace_relations(word, WordParonym, 'related_word', split_values(item.get('paronyms') or item.get('paronim')))
        _replace_relations(word, WordUsageArea, 'area', split_values(item.get('field_uz')) + split_values(item.get('field_en')), attr='area')

        if index % 100 == 0:
            db.session.commit()

    db.session.commit()
    _set_meta('dataset_version', dataset_version)
    _set_meta('dataset_records', str(len(data)))
    _set_meta('blob_matches', str(images))
    return {
        'synced': True,
        'created': created,
        'updated': updated,
        'records': len(data),
        'image_matches': images,
    }