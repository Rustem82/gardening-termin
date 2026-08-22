import json
from app import app, db
from models import Word, WordCategory, WordSynonym, WordAntonym, WordHyperonym, WordHyponym, WordHolonym, \
    WordMeronym, WordHomonym, WordParonym, WordUsageArea

def import_from_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    with app.app_context():
        total = len(data)
        print(f"Начинаем импорт {total} записей...")

        for idx, item in enumerate(data, 1):
            try:
                word_text = None
                for key in ['uzbek', 'word', 'Qishloq xo\'jaligi terminlari', 'soz', 'name']:
                    if key in item and item[key]:
                        word_text = str(item[key]).strip().lower()
                        break

                if not word_text:
                    continue

                definition = item.get('Izohi', '') or item.get('определение', '') or item.get('definition', '') or item.get('definition_uz', '')
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
                    etymology_en=etymology_en
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

                sinonim = item.get('sinonimi (ma\'nodoshi)', '') or item.get('sinonimi', '') or item.get('synonyms_uz', '')
                if sinonim:
                    added_syns = set()
                    for syn in str(sinonim).split(','):
                        syn = syn.strip()
                        if syn and syn.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-', '—']:
                            if syn not in added_syns:
                                added_syns.add(syn)
                                if not WordSynonym.query.filter_by(word_id=word.id, related_word=syn).first():
                                    db.session.add(WordSynonym(word_id=word.id, related_word=syn))

                antonim = item.get('antonimi (zid ma\'nosi)', '') or item.get('antonimi', '') or item.get('antonyms_uz', '')
                if antonim:
                    added_ants = set()
                    for ant in str(antonim).split(','):
                        ant = ant.strip()
                        if ant and ant.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '', '-', '—']:
                            if ant not in added_ants:
                                added_ants.add(ant)
                                if not WordAntonym.query.filter_by(word_id=word.id, related_word=ant).first():
                                    db.session.add(WordAntonym(word_id=word.id, related_word=ant))

                giperonim = item.get('giperonimi (jins)', '') or item.get('giperonimi', '') or item.get('гиперонимы', '') or item.get('hyperonyms', '')
                if giperonim:
                    added_hyps = set()
                    for hyp in str(giperonim).split(','):
                        hyp = hyp.strip()
                        if hyp and hyp.lower() not in ['yo\'q', 'yoq', 'нет', 'none', '']:
                            if hyp not in added_hyps:
                                added_hyps.add(hyp)
                                if not WordHyperonym.query.filter_by(word_id=word.id, related_word=hyp).first():
                                    db.session.add(WordHyperonym(word_id=word.id, related_word=hyp))

                giponim = item.get('giponimi (tur)', '') or item.get('giponimi', '') or item.get('гипонимы', '') or item.get('hyponyms', '')
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

                paronim = item.get('paronimi (talaffuzdoshi)', '') or item.get('paronim', '') or item.get('paronyms', '')
                if paronim and paronim not in [None, 'null', 'None', '']:
                    added_pars = set()
                    for par in str(paronim).split(','):
                        par = par.strip()
                        if par and par.lower() not in ['yo\'q', 'yoq', 'нет', 'none', 'null', '']:
                            if par not in added_pars:
                                added_pars.add(par)
                                if not WordParonym.query.filter_by(word_id=word.id, related_word=par).first():
                                    db.session.add(WordParonym(word_id=word.id, related_word=par))

                usage_uz = item.get('qaysi sohada qo\'llanilishi', '') or item.get('qaysi sohada qollanilishi', '') or item.get('qollanilishi', '') or item.get('field_uz', '')
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

                if idx % 50 == 0:
                    db.session.commit()
                    print(f"✅ {idx}/{total} so'z import qilindi...")

            except Exception as e:
                print(f"❌ Xatolik '{item.get('uzbek', 'unknown')}': {e}")
                continue

        db.session.commit()
        print(f"✅ Import tugadi! Jami {total} ta yozuv.")

if __name__ == '__main__':
    import_from_json('tabl.json')