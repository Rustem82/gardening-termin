# import_all_words.py
from app import app
from models import db, Word
import json


def import_all_words():
    with app.app_context():
        count = Word.query.count()
        print(f'📊 Сейчас в БД: {count} слов')

        with open('yangi.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        added = 0
        for item in data:
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
            added += 1

            if added % 50 == 0:
                db.session.commit()
                print(f'✅ Добавлено {added} слов...')

        db.session.commit()
        print(f'✅ Всего добавлено {added} слов')
        print(f'📊 Итого в БД: {Word.query.count()} слов')


if __name__ == '__main__':
    import_all_words()