from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_login import LoginManager, current_user
from config import Config
from models import db, Word, WordCategory, WordSynonym, WordAntonym, WordHyperonym, WordHyponym, WordHolonym, \
    WordMeronym, WordHomonym, WordParonym, WordUsageArea, Visit, UserVisit
from admin import admin_bp, create_admin
from data_sync import ensure_word_columns, sync_dataset
from datetime import datetime
from sqlalchemy.orm import selectinload
import os

app = Flask(__name__)
app.config.from_object(Config)

# Site interface language is independent from the language of an individual alias.
@app.route('/set-language/<lang>')
def set_language(lang):
    if lang not in ('uz', 'en'):
        return redirect(url_for('index'))
    session['site_lang'] = lang
    destination = request.args.get('next', '/')
    # Only allow internal relative URLs (prevent open redirects).
    if not destination.startswith('/') or destination.startswith('//') or '\\' in destination:
        destination = '/'
    return redirect(destination)

# Dictionary direction is independent of the interface language.
@app.route('/set-dictionary-direction/<direction>')
def set_dictionary_direction(direction):
    if direction not in ('uz-en', 'en-uz'):
        return redirect(url_for('index'))
    session['dictionary_direction'] = direction
    destination = request.args.get('next', '/')
    if not destination.startswith('/') or destination.startswith('//') or '\\' in destination:
        destination = '/'
    return redirect(destination)

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


# ========== DATABASE BOOTSTRAP ==========
def bootstrap_database():
    """Create missing tables/columns and synchronize the packaged dataset once per version."""
    db.create_all()
    ensure_word_columns()
    create_admin()
    if app.config.get('AUTO_SYNC_DATA', True):
        result = sync_dataset(app)
        app.logger.info("Dataset sync: %s", result)


with app.app_context():
    bootstrap_database()


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
        words = Word.query.filter(Word.word.ilike(f'{letter}%'), ~Word.word.startswith('_category_placeholder_')).order_by(Word.word).all()

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
    direction = request.args.get('direction')
    if direction in ('uz-en', 'en-uz'):
        session['dictionary_direction'] = direction
    direction = session.get('dictionary_direction')
    results = []

    if query:
        try:
            # Search headwords, English translations and semantic aliases.
            # Unicode normalization also makes o‘ / o' apostrophes equivalent.
            normalized_query = _normalize_term(query)
            words = []
            matching_aliases = {}
            relation_names = ('synonyms', 'antonyms', 'hyperonyms', 'hyponyms',
                              'holonyms', 'meronyms', 'homonyms', 'paronyms')
            # Eager-load relation collections in batches instead of one query per word.
            search_query = Word.query.options(
                *(selectinload(getattr(Word, name)) for name in
                  ('synonyms', 'antonyms', 'hyperonyms', 'hyponyms',
                   'holonyms', 'meronyms', 'homonyms', 'paronyms', 'usage_areas'))
            ).filter(~Word.word.startswith('_category_placeholder_'))
            for candidate in search_query.all():
                labels = [candidate.word, candidate.translation_en or '']
                aliases = []
                for relation_name in relation_names:
                    for relation in getattr(candidate, relation_name):
                        aliases.extend(part.strip() for part in
                                       (relation.related_word or '').split(';') if part.strip())
                matching_alias = next((alias for alias in aliases
                                       if normalized_query in _normalize_term(alias)), None)
                matches = (any(normalized_query in _normalize_term(label) for label in labels)
                           or any(normalized_query in _normalize_term(area.area)
                                  for area in candidate.usage_areas)
                           or matching_alias is not None)
                if matches:
                    words.append(candidate)
                    if matching_alias:
                        matching_aliases[candidate.id] = matching_alias

            # Сортировка: точное совпадение слова, начало слова, затем остальные
            def sort_words(word_obj):
                word_lower = _normalize_term(word_obj.word)
                query_lower = normalized_query
                if _normalize_term(matching_aliases.get(word_obj.id, '')) == query_lower:
                    return (-1, word_lower)
                if word_lower == query_lower:
                    return (0, word_lower)
                elif word_lower.startswith(query_lower):
                    return (1, word_lower)
                else:
                    return (2, word_lower)

            words = sorted(words, key=sort_words)

            for word in words:
                # Category is a dynamic relationship in this application.
                first_category = word.categories.first()
                results.append({
                    'word': word.word,
                    'matched_alias': matching_aliases.get(word.id),
                    'search_lang': ('en' if direction == 'en-uz' else 'uz') if direction in ('uz-en', 'en-uz') else ('en' if _related_term_language(query) == 'en' else 'uz'),
                    'part_of_speech_uz': first_category.category if first_category else '',
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

def _normalize_term(value):
    """Normalize URL/database term text without changing the stored spelling."""
    import unicodedata
    from urllib.parse import unquote

    value = unquote(str(value or ''))
    value = unicodedata.normalize('NFKC', value)
    value = value.replace('’', "'").replace('‘', "'").replace('ʻ', "'").replace('ʼ', "'").replace('`', "'")
    return ' '.join(value.split()).strip().casefold()


def _find_word_by_url_term(value):
    """Find a term robustly: spaces, URL encoding, case and apostrophe variants are tolerated."""
    from sqlalchemy import func
    from urllib.parse import unquote

    decoded = ' '.join(unquote(str(value or '')).split()).strip()
    if not decoded:
        return None

    # Fast path for PostgreSQL/SQLite.
    item = Word.query.filter(
        func.lower(func.trim(Word.word)) == decoded.lower()
    ).first()
    if item:
        return item

    # Unicode/apostrophe-safe fallback. 1100 rows is small enough for this fallback.
    target = _normalize_term(decoded)
    for item in Word.query.filter(~Word.word.startswith('_category_placeholder_')).all():
        if _normalize_term(item.word) == target:
            return item
    return None



# English synonym labels extracted from the bilingual source dataset.
# This keeps language classification accurate even though the SQL relations are merged.
_ENGLISH_SYNONYMS = ('-', 'Abiotic diseases', 'Absorptive fine roots', 'Acclimate', 'Acicular leaf', 'Aerosol irrigation', 'Agricultural biology', 'Agricultural chemistry', 'Agricultural experiment station', 'Agricultural frost', 'Agricultural logistics', 'Agronomic chemistry', 'Aleyrodid', 'Allelomorphic characters', 'Alligator pear', 'Almond plantation', 'Amazon waterlily', 'American Judas tree', 'American blight', 'American redbud', 'Ammonia fertilizer', 'Ammonium sulphate', 'Anemochores', 'Anemophiles', 'Annuals', 'Anthocyan', 'Apical meristems', 'Apple aphid', 'Apple leaf miner', 'Apple powdery mildew', 'Apple woolly aphid', 'Arbour system', 'Artichoke', 'Asexual propagation', 'Asiatic elm', 'Atmospheric humidity', 'Aubergine, brinjal', 'Austrian pine', 'Autoclave', 'Autumn ploughing', 'Autumnal', 'Azotobacter inoculant', 'BHC', 'Babylon weeping willow', "Bachelor's button", 'Bacterial biofertilizers', 'Barren', 'Bed porosity', 'Beet producer', 'Bench grafting', 'Benzene hexachloride', 'Berry', 'Berry production', 'Biochromes', 'Biocontrol laboratory', 'Biofactory', 'Biological control', 'Biological pigments', 'Biotic environment', 'Biparental cross', 'Bitter orange', 'Blaeberry', 'Bloom period', 'Blossom', 'Bluebottle', 'Branch', 'Branch out', 'Branch roots', 'Breeder', 'Broadleaf tree', 'Brown fruit mite', 'Brown rot of fruit trees', 'Bunch', 'Bush', 'Bushland', 'Bushy', 'Cabbage family', 'Cabbage white butterfly', 'California scale', 'Californian scale', 'Calla', 'Canada goldenrod', 'Caragana', 'Carbamide', 'Carbonyl diamide', 'Carpellum', 'Cascade', 'Casebearer moth', 'Cellular respiration', 'Chasteberry', 'Check variety', 'Chemical composition of soil', 'Chemical pest control', 'Cherry slug', 'Chestnut genus', 'Chile saltpeter', 'Chilli pepper', 'Chinar tree', 'Chinese arborvitae', 'Chinese date', 'Chinese jujube', 'Chinese persimmon', 'Chisel tillage', 'Citrus greenhouse', 'Citrus house', 'Climacteric', 'Climbers', 'Clone selection', 'Cola nut', 'Cola tree', 'Cold-storage facilities', 'Cold-tolerant', 'Coleopterans', 'Colorado beetle', 'Common apricot', 'Common bird cherry', 'Common cypress', 'Common hollyhock', 'Common honey-locust', 'Common horse-chestnut', 'Common jujube', 'Common medlar', 'Common olive', 'Common peach', 'Common plum', 'Common quince', 'Common walnut', 'Common white jasmine', 'Compound winter bud', 'Concentrated fertilizers', 'Conifers', 'Conservatory', 'Contrasting characters', 'Copper-lime mixture', 'Coryneum blight', 'Crested celosia', 'Crop harvesting', 'Cross-fertilization', 'Cruciferae', 'Cultivar testing', 'Cultivar-specific', 'Cultivated apple', 'Cultivated garlic', 'D-glucose', 'Daffodil', 'Dahlia', 'Decorative', 'Decorative horticulture', 'Decorative plants', 'Dendropark', 'Depth of irrigation', 'Detached scion grafting', 'Dextrose', 'Dicots', 'Dicotyledons', 'Disease process', 'Dogrose', 'Donut peach', 'Dormant pruning', 'Dormant-season pruning', 'Double grafting', 'Double raceme', 'Doucin rootstock', 'Doughnut peach', 'Dried grape', 'Dried plum', 'Drupes', 'Dwarf elm', 'Dwarf quince', 'Dwarf rootstock', 'Eastern plane', 'Edible fig', 'Elderberry', 'English lilac', 'Epicarp', 'Epicormic shoots', 'Essential-oil-bearing roses', 'European bird cherry', 'European black pine', 'European cabbage white', 'European gooseberry', 'European horse-chestnut', 'European medlar', 'European olive', 'European pear psylla', 'European plum', 'European raspberry', 'European snowball viburnum', 'European spruce', 'European vine moth', 'Everbearing', 'Eye', 'Facultative saprophytes', 'Fall plowing', 'False acacia', 'False fruit', 'Fertiliser (BrE)', 'Fertilizer application through irrigation', 'Fertilizer rate', 'Field storage clamp', 'Fig', 'Fig leaf roller', 'Fig moth', 'Fig plantation', 'Fig-leaf skeletoniser', 'Floral bud', 'Floral shears', 'Floral snips', 'Flower', 'Flower cluster', 'Flower cultivation', 'Flower stalk', 'Flower thinning', 'Fluid fertilizers', 'Foliar fertilization', 'Foliar necrosis', 'Formal compositions', 'French lilac', 'Fruit Preserve', 'Fruit culture', 'Fruit jelly', 'Fruit nursery', 'Fruit sugar', 'Fruit tree spider mite', 'Fruit-bearing branches', 'Fruiting', 'Furrow', 'F₁ hybrid seed', 'Gall', 'Garden hoe', 'Garden strawberry', 'Garden turnip', 'German chamomile', 'Germination percentage', 'Giant waterlily', 'Glasshouse', 'Goat-leaf honeysuckle', 'Golden rain tree', 'Grape berry moth', 'Grape bunch', 'Grape fruit moth', 'Grape grower', 'Grape growing', 'Grape pip', 'Grape powdery mildew', 'Grape wine', 'Grapevine phylloxera', 'Grapevine powdery mildew', 'Grasshoppers', 'Green plum', 'Greenhouse cultivation', 'Greenhouse farming', 'Greenhouse plants', 'Greening', 'Greens', 'Greenwood grafting', 'Grey cabbage aphid', 'Growth retardant', 'Gum', 'Gumming', 'Hand hoeing', 'Hand pruners', 'Head cabbage', 'Heater-based frost protection', 'Hedging', 'Hot pepper', 'Hybrid vigor', 'Hydro-edaphic factors', 'Hygrophilous plants', 'Immune variety', 'Informal landscape style', 'Inorganic fertilizers', 'Insect science', 'Insect-pollinated plants', 'Insecticidal agents', 'Intensive orchards', 'Interparticle porosity', 'Interstock grafting', 'Irrigation dose', 'Irrigation furrow', 'Isopterans (traditional taxonomic term)', 'Italian cypress', 'Italian poplar', 'Japanese flowering quince', 'Japanese quince', 'Jessamine', 'Jujube fruit fly', 'June beetles', 'June bugs', 'Juniper woodland', 'Juvenile phase', 'Kaki', 'Kaki persimmon', 'Kolomikta vine', 'Lacewings', 'Lateral bud', 'Leaf abscission', 'Leaf stalk', 'Leafy greens', 'Lemon', 'Lepidopterans', 'Level and smooth the soil', 'Levulose', 'Light-demanding plants', 'Lilac', 'Lily tree', 'Little-leaf linden', 'Littleleaf linden', 'Localized enlargement', 'Long narrow flower bed', 'Main branches', 'Male gamete', 'Mandarin orange', 'Marvel of Peru', "Maule's quince", 'May beetles', 'May-tree', 'Meadow orcharding', 'Mealy cabbage aphid', 'Medium-maturing', 'Medlar', 'Medulla', 'Meristematic tissue', 'Mexican lime', 'Microelements', 'Microfertilizers', 'Micropropagation', 'Mid-maturing', 'Mignonette tree', 'Mineral substances', 'Miticides', 'Mn fertilizers', 'Monilinia brown rot', 'Moniliosis', "Monk's pepper", 'Monocropping', 'Monoecious species', 'Morphological characters', 'Mountain ash', 'Mulberries', 'Mulberry cultivation', 'Mulberry orchard', 'Musaceae', 'Mustard family', 'Mycoplasma-like organisms (MLOs', 'Naked magnolia', 'Narcobiosis', 'Narrow-leaf oleaster', 'Native plants', 'Naturalistic garden style', 'Nectar gland', 'Nitrate of soda', 'Non-fruiting', 'Noncambial roots', 'Normal atmosphere storage (NA)', 'North American redbud', 'Nursery', 'Nursery stock', 'Nutritional value', 'Obligate biotrophs', 'Obligatory parasites', 'Oenology', 'Offspring', 'Oidium', 'Olive grove', 'Olive scale', 'Ontogenesis', 'Orange', 'Orchard smoking', 'Oriental persimmon', 'Packing', 'Palmette system', 'Parasitic angiosperms', 'Parks and gardens', 'Partial ripeness', 'Pasteurisation (BrE)', 'Pea-tree', 'Pear and cherry slugworm', 'Pear psyllid', 'Pear sawfly', 'Pear tingid', 'Pekmez', 'Perennials', 'Perfoliate honeysuckle', 'Pergola system', 'Perianthium', 'Permanent apple aphid', 'Permanent storage structures', 'Pernicious scale', 'Persian walnut', 'Phenological monitoring', 'Phosphate element', 'Phosphate fertilizers', 'Phosphate-containing', 'Phosphatic fertilizers', 'Photoperiodicity', 'Photophilic', 'Photophilous plants', 'Phreatic water', 'Physical loss', 'Phytopathogen', 'Phytopathological examination', 'Phytosanitary laboratory', 'Phytotomy', 'Pinch', 'Pinks', 'Planipennia', 'Plant Pathology', 'Plant Terrarium', 'Plant bud', 'Plant epidemic', 'Plant growth', 'Plant growth regulators (PGRs)', 'Plant hair', 'Plant hormones', 'Plant introduction nursery', 'Plant lice', 'Plant nursery production', 'Plant sap', 'Plant-feeding insects', 'Planting seed', 'Planting time', 'Plough (BrE)', "Poet's jasmine", "Poet's jessamine", 'Pollard knuckle', 'Pollen parent', 'Pomegranate moth', 'Pomegranate plantation', 'Pomes', 'Postgenerative period', 'Postharvest storage technology', 'Pot culture method', 'Potash fertilizers', 'Potato cultivation', 'Potato farming', 'Powdery mildew of peach', 'Preventive actions', 'Preventive practices', 'Privet', 'Productive', 'Proterogyny', 'Protuberance', 'Prune moth', 'Pruning paint', 'Pruning shears', 'Pseudocarp', 'Punicaceae', 'Pyrene', 'Quality loss', 'Quickthorn', 'Quince plantation', 'Reach maturity', 'Red date', 'Red juniper', 'Red plum maggot', 'Red raspberry', 'Redbud', 'Refrigerated stores', 'Rejuvenating pruning', 'Rejuvenescence', 'Renovation pruning', 'Resistance to disease', 'Respiration climacteric', 'Rhizoctonia root disease', 'Ribbon flower bed', 'Rind grafting', 'Rockery', 'Root vegetables', 'Rootstock-scion compatibility', 'Rosa canina fruit', 'Rose bay', 'Rose moss', 'Rosehip', 'Rosmarina Bianca apple cultivar', 'Rotational cropping', 'Roundworms', 'Saccharose', 'Sage', 'Salinity tolerance', 'Sandthorn', 'Sanitation pruning', 'Saprobe', 'Saprophyte', 'Savin', 'Scab', 'Sciophilous', 'Scolytine beetles', 'Scorch', 'Scotch pine', 'Sea buckthorn berry', 'Seabuckthorn', 'Seed parent', 'Seed scarification', 'Seed storehouse', 'Self-digestion', 'Self-pollination', 'Self-unfruitful', 'Semelparous plants', 'Semi-open drying shed', 'Semishrubs', 'Shelterbelt trees', 'Shield budding', 'Shoot pinching', 'Shoot trimming', 'Short-horned grasshoppers', 'Shot-hole of stone fruit', 'Shothole blight', 'Sierra redwood', 'Silverberry family', 'Simple sugars', 'Single-flowered plants', 'Slender magnolia', 'Small cabbage white', 'Small leaf lime tree', 'Small white', 'Smudging', 'Snowball tree', 'Soda niter', 'Soft scale insects', 'Soil ball', 'Soil leveler', 'Soil tillage', 'Sowing seed', 'Specimen', 'Spiraea', 'Split grafting', 'Split-root system', 'Spray irrigation', 'Spring ploughing', 'Spring radish', 'Sprout', 'Stock', 'Stratification (seed)', 'Sub-irrigation', 'Sub-scaffold branches', 'Succulent plants', 'Sucker', 'Suffrutices', 'Sulfur-containing fertilizers', 'Sulphur', 'Summer jasmine', 'Summer radish', 'Suspended animation', 'Sweet locust', 'Sweet-cherry spider mite', 'Syrian privet', 'T trellis', 'Tagetes', 'Tart', 'Tart cherry', 'Tart cherry fruit', 'Technological characteristics', 'Temporary storage facilities', 'Ten-lined potato beetle', 'Ten-striped spearman', 'Testcross', 'Thermophilous', 'Thin', 'Thornapple', 'Thysanopterans', 'To leaf', 'Transport fine roots', "Traveller's palm", 'Tree and shrub mass', 'Tree wound dressing', 'Trial field', 'Trickle irrigation', 'True bugs', 'True flies', 'True jasmine', 'Tulip poplar', 'Tuliptree', 'Typical aphids', 'Undershrubs', 'Understock', 'Uniflorous plants', 'Unripe apricot', 'Ureaform fertilizers', 'Value in use', 'Variety replacement', 'Vascular wilt disease', 'Vase-shaped system', 'Vegetable cultivation', 'Vegetable growing', 'Vegetable production', 'Vegetative reproduction', 'Vegetatively propagated rootstock', 'Vertical landscaping', 'Victoria regia', 'Vine', 'Vine arbor', 'Vine growing', 'Vine moth', 'Vine pruning', 'Viral diseases', 'Virginia red cedar', 'Virginile ontogenetic state', 'Vitex', 'Void fraction', 'Walnut grove', 'Walnut moth', 'Water cascade', 'Watershoots', 'Weedkillers', 'West Indian lime', 'Whortleberry', 'Wilt disease', 'Wind-dispersed plants', 'Wind-pollinated plants', 'Wisteria', 'Y-trellis', 'Yellowing', 'Yulan', 'air storage', 'apple tree', 'brown apple mite', 'bryobia mite', 'coccids', 'common pear psyllid', 'historical)', 'host resistance to diseases', 'pear bryobia', 'pear sucker', 'pearlace bug', 'yellow poplar')
_UZBEK_SYNONYMS = ('-', 'Abiotik faktorlar', 'Achchiq apelsin', 'Achchiq qalampir', 'Agrokimyoviy laboratoriya', 'Agrotexnik usul', 'Ajdargul', 'Alligator noki', 'Amerika lola daraxti', 'Ammiakli selitra', 'Anemofillar', 'Anemoxorlar', 'Anjir bog‘i', 'Anor bog‘i', 'Anor mevaxo‘ri', 'Anorganik omillari', 'Anorlar oilasi', 'Aralash gulzor', 'Archa o‘rmoni', 'Arg‘uvon', 'Asosiy shoxlar', 'Atirguldoshlar', 'Atmosfera namligi', 'Autoliz', 'Bachki novdalar', 'Bachkilamoq', 'Balx tut', 'Barg burishishi', 'Barg chiqarmoq', 'Barg kovlovchi kuyalar', 'Barg orqali oziqlantirish', 'Barg tashlash', 'Bargda mina yasovchi kuyalar', 'Bargini to‘kuvchi daraxt', 'Baxmalgul', 'Behi bog‘i', 'Behosil', 'Bel', 'Beorgul', 'Binafsha tusli qalqondor', 'Biologik kurash', 'Biologik laboratoriya', 'Biologik nazorat', 'Biopreparatlar', 'Biotroflar', 'Bir gullilar', 'Bir uylilar', 'Bir yilliklar', 'Birlamchi urug‘chilik', 'Biryuchina', 'Boboi', 'Bodom bog‘i', 'Bog‘ anjomlari', 'Bog‘ asbob-uskunalari', 'Bog‘ surtkisi', 'Bog‘-tok qator oralari ekinlari', 'Bog‘bonlik', 'Bog‘chi', 'Bog‘lar va parklar', 'Bog‘ni isitish', 'Bog‘ni tutunlatish', 'Boldirg‘on', 'Bolut', 'Bordo aralashmasi', 'Bosh karam', 'Bosh piyoz', 'Bo‘rli o‘g‘itlar', 'Bo‘tako‘z', 'Buldurg‘un', 'Buzina', 'Chalabutalar', 'Chatishtirmoq', 'Chechak', 'Chili selitrasi', 'Chilon', 'Chimzor', 'Chirindi', 'Chirmashib o‘suvchi o‘simliklar', 'Chirmovgul', 'Choy-duragay atirgullar', 'Danakli daraxtlar', 'Danakmevalilar', 'Daraxt qobig‘i', 'Daraxt-buta massivi', 'Daraxtshunoslik', 'Dastlabki urug‘chilik', 'Dekorativ bog‘dorchilik', 'Dekorativ o‘simliklar', 'Dekstroza', 'Dendrariy', 'Dendrologik bog‘', 'Dioekik o‘simliklar', 'Dovcha', 'Duragay', 'Duragay quvvati', 'Duragaylamoq', 'Duragaylash', 'Dusen payvandtagi', 'Duvarak novdalar', 'Duzen', 'Egat olmoq', 'Egatlab ekish', 'Egatlab sug‘orish', 'Ekish vaqti', 'Embrion', 'Enologiya', 'Entomotsidlar', 'Enzimlar', 'Epikarp', 'Fakultativ saprofitlar', 'Faol ildizlar', 'Fasl', 'Fitotomiya', 'Fiziologik tinim', 'Florikultura', 'Formal kompozitsiyalar', 'Fosfatli o‘g‘itlar', 'Fosfor elementi', 'Fotoperiodizm', 'Geksaxlorsiklogeksan (HCH)', 'Geliofitlar', 'Generativ', 'Generativ kurtak', 'Georgina', 'Gibrid', 'Gibrid quvvati', 'Gibrid urug‘', 'Gibridizatsiya', 'Gibridlash', 'Gibridlashtirmoq', 'Gigant sekvoyyadendron', 'Gilos bog‘i', 'Gleditsiya', 'Glitsiniya', 'Gorizontal parxishlash', 'Granulalash', 'Grek yong‘og‘i', 'Gul ochmoq', 'Gul toji', 'Gulasal', 'Gulbog‘', 'Gulg‘uncha', 'Gullash bosqichi', 'Gullash fazasi', 'Gunafsha', 'G‘aynoli', 'Hamisha yashil daraxt', 'Hasharotlarga qarshi preparatlar', 'Hasharotshunoslik', 'Havo muhitida saqlash', 'Himoya daraxtlari', 'Hoshiya qanotlilar', 'Hosil novdasi', 'Hosil qiluvchi to‘qima', 'Hosil shoxlari', 'Hosildor', 'Hosilni yig‘ishtirish', 'Hujayra muhandisligi', 'Ignabarglilar', 'Ikki urug‘pallalilar', 'Ikki uylilar', 'Ildiz komi', 'Ildiz tuklari', 'Ildizmevali ekinlar', 'Ildizmevalilar guruhi', 'Ilono‘ti', 'Individual rivojlanish', 'Iris', 'Isitish orqali sovuqdan himoyalash', 'Issiqsevar', 'Issiqxona ekinlari', 'Jadal', 'Jo‘yak', 'Jo‘yak usulida ekish', 'Jumrutsimon chakanda', 'Kalibrlovchi mashinalar', 'Kaliks', 'Kalina', 'Kallak urmoq', 'Kallaklangan', 'Kallus', 'Kapalaklar', 'Kaprifol', 'Karantin laboratoriyasi', 'Karpel', 'Kartoshka qo‘ng‘izi', 'Kartoshka yetishtirish', 'Kasallik jarayoni', 'Keng bargli daraxt', 'Keng yaproqli daraxt', 'Kichik ariq', 'Kimyoviy kurash usuli', 'Klimaks', 'Klimakterik davr', 'Klimakterik yuksalish', 'Klontashtirish', 'Kola urug‘i', 'Kolomikta', 'Kompost tayyorlamoq', 'Korolla', 'Kosmos guli', 'Ko‘chat yetishtirish', 'Ko‘chirib ekmoq', 'Ko‘k vasilek', 'Ko‘katlar', 'Ko‘p urug‘li', 'Ko‘p yilliklar', 'Ko‘z payvand', 'Krestgullilar', 'Ksenogamiya', 'Kuchaytirilgan', 'Kuzgi haydash', 'Landshaft kompozitsiyasi', 'Landshaft uslubi', 'Leman zarpechagi', 'Levuloza (eskirgan ilmiy nom)', 'Manzarali', 'Marmarak', 'Marvak tut', 'Mavrak', 'Mavsumiy omborlar', 'Mayda bargli qayrag‘och', 'Maysazor', 'Meva beruvchi', 'Meva kurtagi', 'Mevali o‘simliklar ko‘chatzori', 'Mexanik kurash', 'Mikoplazmasimon organizmlar (MLO', 'Mikroklonal ko‘paytirish', 'Mikronutrientlar', 'Miqdoriy yo‘qotish', 'Mis-ohak aralashmasi', 'Mochevina', 'Modulli bog‘-chaman', 'Mola bosmoq', 'Moychechak', 'Nafas olish jarayoni', 'Nastarin', 'Natriy nitrat', 'Nav sinovi', 'Nektar bezi', 'Nok bog‘i', 'Nok shira burgasi', 'Oddiy bodrezak', 'Oddiy olcha', 'Oftobda quritish', 'Og‘izcha', 'Okulirovka', 'Olcha bog‘i', 'Oldini olish tadbirlari', 'Oleandr', 'Olhirot', 'Olma bog‘i', 'Olma qandalasi', 'Olma va nok un-shudringi', 'Olu', 'Olxo‘ri qurti', 'Ommaviy tanlash', 'Ona shakl', 'Oq akatsiya', 'Oq pashsha', 'Organik omillar', 'Ot kashtani', 'Ota shakl', 'Oziq-ovqatlik qiymati', 'Oziqaviy qiymati', 'O‘g‘it bermoq', 'O‘g‘it me’yori', 'O‘g‘it solmoq', 'O‘lchamiga qarab xillash', 'O‘rik bog‘i', 'O‘simlik bitlari', 'O‘simlik gormonlari', 'O‘simlik kasalliklari epidemiyasi', 'O‘simliklar karantini', 'O‘simliklar patologiyasi', 'O‘simlikni ajratilgan muhitda oziqlantirish', 'O‘simlikxo‘r hasharotlar', 'O‘sish nuqtalari', 'O‘sish regulyatorlari', 'O‘sish retardanti', 'O‘suv davri', 'O‘suvchi shoxlar', 'O‘tloq qandalasi', 'O‘z-o‘zidan changlanish', 'Pakana meva daraxtlari', 'Pakana qayrag‘och', 'Parazit gulli o‘simliklar', 'Parsha', 'Parterli gulzor', 'Parvarish qilmoq', 'Pashshalar', 'Past bo‘yli daraxtlar bog‘i', 'Past bo‘yli meva daraxtlari', 'Past bo‘yli payvandtag', 'Patogen', 'Payvand qilingan', 'Payvand qilmoq', 'Pekan yong‘og‘i', 'Periant', 'Pishmagan', 'Pishmagan meva', 'Pista bog‘i', 'Pitomnik', 'Piyozboshli o‘simliklar', 'Plastinali kurtak payvand', 'Pog‘onali sharshara', 'Polen', 'Pona payvand', 'Po‘stloq ostiga payvand', 'Po‘stloqxo‘r qo‘ng‘izlar', 'Profilaktik chora-tadbirlar', 'Proteroginiya', 'Qabariq', 'Qalamcha payvand', 'Qalampir', 'Qandalalar', 'Qandil', 'Qarama-qarshi belgilar', 'Qarama-qarshilik', 'Qayta tiklanish', 'Qishloq xo‘jaligi kimyosi', 'Qora smorodina', 'Qoraqat', 'Qo‘ng‘izlar', 'Qo‘sh payvand', 'Qo‘shqanotlilar', 'Quraga', 'Quritilgan olma', 'Quritilgan olxo‘ri', 'Quritilgan o‘rik', 'Quritilgan uzum', 'Quyoshda quritish', 'Ranglar mutanosibligi', 'Ranglar uyg‘unligi', 'Ra’nodoshlar', 'Reproduktiv shoxlar', 'Respiratsiya', 'Rezavorfurush', 'Rezavorlar', 'Rizoktonioz', 'Sabzavotchi', 'Samarali harorat', 'Saprob', 'Saprofit', 'Sapsargul', 'Seleksion ko‘chatzor', 'Seleksiyachi', 'Seleksiyachilik', 'Semiz o‘tlar', 'Senoanabioz', 'Serbarg', 'Serhosil', 'Serunum', 'Serunum tuproq', 'Shaftoli un-shudringi', 'Shalfey', 'Shamol orqali tarqaluvchi o‘simliklar', 'Shamol to‘suvchi daraxtlar', 'Sharob', 'Sharobbop uzum', 'Sharq xurmosi', 'Shiradon', 'Shirador', 'Shisha bog‘', 'Shox chiqarmoq', 'Shox otmoq', 'Shoxlamoq', 'Sho‘rlanishga chidamlilik', 'Shudgorlamoq', 'Sifat o‘zgarishidagi yo‘qotish', 'Sifati me’yorlari', 'Sitrus issiqxonasi', 'Sitruslar', 'Siyraklab ko‘chirib o‘tkazish', 'Siyraklashtirmoq', 'Smorodina', 'Sovun daraxti', 'Sovuqbardosh', 'Sovuqqa bardoshli', 'Sovutgichli omborlar', 'Soxta kashtan', 'Soyabardosh', 'Soyaga bardoshli', 'So‘lish kasalligi', 'Spireya', 'Statsionar omborlar', 'Stoma', 'Subirrigatsiya', 'Sug‘orish normasi', 'Sug‘orish orqali o‘g‘itlash', 'Sug‘orish shoxobchalari', 'Sug‘orish sistemasi', 'Supurgi kelreyteriya', 'Suv-tuproq omillari', 'T-simon payvand', 'T-simon simbag‘az', 'Tahliliy chatishtirish', 'Tanidlar', 'Tasma gulzor', 'Temperatura', 'Teplitsa', 'Teplitsa xo‘jaligi', 'Teshikli dog‘lanish', 'Tik ildizlar', 'Tik ko‘kalamzorlashtirish', 'Tikanli gleditsiya', 'Tinish holati', 'Tirak', 'Tirgak', 'Tojbarg', 'Tok fillokserasi', 'Tok qaychisi', 'Tok un-shudringi', 'Tokchilik', 'Tokni butash', 'Tokning un-shudring kasalligi', 'Tokshunoslik', 'Tokzor', 'Tolerantlik', 'Toshli bog‘', 'To‘pgul', 'Trixoma', 'Tub o‘simliklar', 'Tubulg‘a', 'Tukcha', 'Tuksiz shaftoli', 'Tumanli sug‘orish', 'Tuproq chirindisi', 'Tuproq kislotaliligi', 'Tuproq komi', 'Tuproqqa ishlov berish', 'Tut bog‘i', 'Tutun bilan sovuqdan himoyalash', 'Uch tikanli gleditsiya', 'Unabi', 'Unib chiqmoq', 'Unifatsial barg', 'Unnobi', 'Unobi pashshasi', 'Unshudring kasalligi', 'Urug‘ hosil qilmoq', 'Urug‘ ko‘chatzori', 'Urug‘chi tumshuqchasi', 'Urug‘chi ustunchasi', 'Urug‘chibarg', 'Urug‘lanishsiz meva hosil bo‘lishi', 'Urug‘murtak', 'Urug‘ni skarifikatsiyalash', 'Uyg‘un', 'Uzib olmoq', 'Uzum donasi', 'Uzum fillokserasi', 'Uzum kuyasi', 'Uzumchilik', 'Uzumxo‘r qurt', 'Uzumzor', 'Valish', 'Vaqtinchalik omborlar', 'Vazasimon shakl', 'Vegetativ ko‘paytirish', 'Vegetativ kurtak', 'Vegetativ payvandtag', 'Vegetativ shoxlar', 'Vegetatsion tajriba usuli', 'Ventilyatsiya', 'Vertikal parxishlash', 'Vertitsillyoz vilt', 'Xayri', 'Xazonrezgi', 'Xillash', 'Xom', 'Xom meva', 'Xo‘jag‘at', 'Yagana qilmoq', 'Yakka ziroatchilik', 'Yakkaxon o‘simlik', 'Yapon behisi', 'Yaproq', 'Yaproq bandi', 'Yarim ochiq quritish bostirmasi', 'Yaruslik', 'Yashil olma biti', 'Yashil o‘g‘it ekini', 'Yashil sarv', 'Yashillashtirish', 'Yassi shaftoli', 'Yelim oqishi', 'Yerli', 'Yertana', 'Yevropa qoraqarag‘ayi', 'Yong‘oq mevaxo‘ri', 'Yoppasiga sug‘orish', 'Yorma payvand', 'Yoshartiruvchi kesish', 'Yoshlik davri', 'Yotiq ildizlar', 'Yovvoyi atirgul', 'Yovvoyi jiyda', 'Yozgi butash', 'Yo‘g‘on poyali zarpechak', 'Yumaloq chuvalchanglar', 'Yuqori konsentratsiyali o‘g‘itlar', 'Yuqori zichlikdagi bog‘lar', 'Yuqumli kasalliklar', 'Yuqumsiz kasalliklar', 'Yuraksimon jo‘ka', 'Zamburug‘li kasalliklar', 'Zang kanasi', 'Zantedeskiya', 'Ziyonkor hasharotlar', 'anor kuyasi', 'bir o‘lchamga keltirish', 'nordon olcha', 'po‘stloq osti qo‘ng‘izlari', 'shaxsiy rivojlanish', 'tarixiy nom)', 'teshikchali dog‘lanish')

def _related_term_language(term):
    """Choose the card language for links when legacy relations lack a language field."""
    import re
    value = _normalize_term(term)
    if not value:
        return 'uz'
    if value in {_normalize_term(x) for x in _ENGLISH_SYNONYMS}:
        return 'en'
    if value in {_normalize_term(x) for x in _UZBEK_SYNONYMS}:
        return 'uz'
    # Explicit aliases from the bilingual source dataset.
    if value in {'soil tillage', 'native plants'}:
        return 'en'
    # Match a stored English headword first.
    for entry in Word.query.filter(Word.translation_en.isnot(None)).all():
        if _normalize_term(entry.translation_en) == value:
            return 'en'
    # Existing data_sync merges synonyms_uz and synonyms_en in one relation table.
    # Recognize English phrases; otherwise default to Uzbek.
    english_words = set('soil tillage native plants plant crop crops cultivation agriculture agricultural tree trees fruit fruits garden gardening water irrigation root roots seed seeds growing growth field fields fertilizer fertilizers chemical chemistry analysis laboratory protection control pest pests biology biological flowers flower leaf leaves grape grapevine orchard horticulture method technique system production management organic mineral genetic genetics breeding winter bud season farming treatment land greenhouse compost harvesting'.split())
    words = set(re.findall(r'[a-z]+', value))
    if words & english_words and not any(ch in value for ch in "o‘gʻq‘"):
        return 'en'
    return 'uz'


@app.template_filter('related_lang')
def related_lang_filter(term):
    return _related_term_language(term)


@app.route('/related-term/<path:term>')
def related_term(term):
    """Resolve a related term to its own dictionary entry, in Uzbek or English."""
    from sqlalchemy import func
    from urllib.parse import unquote

    term = unquote(term).strip()
    target = _find_word_by_url_term(term)
    if target is None:
        # English names are stored in translation_en, not in Word.word.
        target = Word.query.filter(
            func.lower(func.trim(Word.translation_en)) == term.lower(),
            ~Word.word.startswith('_category_placeholder_')
        ).order_by(Word.id).first()
    if target is None:
        normalized = _normalize_term(term)
        for candidate in Word.query.filter(
            Word.translation_en.isnot(None),
            ~Word.word.startswith('_category_placeholder_')
        ).order_by(Word.id):
            if _normalize_term(candidate.translation_en) == normalized:
                target = candidate
                break
    if target is None:
        # Synonyms and other semantic labels can be aliases rather than separate entries.
        # Resolve the alias to the owner entry without changing the database schema.
        normalized = _normalize_term(term)
        relation_models = (
            WordSynonym, WordAntonym, WordHyperonym, WordHyponym,
            WordHolonym, WordMeronym, WordHomonym, WordParonym,
        )
        for relation_model in relation_models:
            if target is not None:
                break
            for relation in relation_model.query.all():
                raw = relation.related_word or ''
                # A relation can contain several labels separated by semicolons.
                labels = [part.strip() for part in raw.split(';')]
                if any(_normalize_term(label) == normalized for label in labels):
                    owner = db.session.get(Word, relation.word_id)
                    if owner and not owner.word.startswith('_category_placeholder_'):
                        target = owner
                        break
    if target is None:
        return render_template('404.html', word_query=term, suggestions=[]), 404
    requested_lang = request.args.get('lang')
    inferred_lang = _related_term_language(term)
    # Legacy links may incorrectly pass lang=uz for an English synonym.
    # Correct known English aliases rather than showing the Uzbek card.
    if _normalize_term(term) in {'soil tillage', 'native plants'}:
        requested_lang = 'en'
    if requested_lang not in ('uz', 'en'):
        requested_lang = inferred_lang
    return redirect(url_for('word_detail', word=target.word, lang=requested_lang))


@app.route('/word/<path:word>')
def word_detail(word):
    try:
        db_word = _find_word_by_url_term(word)
        if not db_word:
            return render_template('404.html', word_query=word, suggestions=[]), 404

        data = {
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
        return render_template('word_detail.html', word=db_word.word, data=data, card_lang=request.args.get('lang') if request.args.get('lang') in ('uz', 'en') else ('en' if session.get('dictionary_direction') == 'en-uz' else 'uz' if session.get('dictionary_direction') == 'uz-en' else 'both'))
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('word_detail failed for %r: %s', word, exc)
        return render_template('500.html'), 500


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

@app.route('/field/<path:field_name>')
def field_page(field_name):
    from urllib.parse import unquote
    from sqlalchemy import or_

    # Иногда ссылка может оказаться закодирована повторно.
    # Например: Agrobiologik%2520asoslar -> Agrobiologik%20asoslar -> Agrobiologik asoslar
    decoded_name = str(field_name or '')
    for _ in range(3):
        new_value = unquote(decoded_name)
        if new_value == decoded_name:
            break
        decoded_name = new_value

    decoded_name = decoded_name.replace('+', ' ')
    decoded_name = ' '.join(decoded_name.split()).strip()

    # В базе поле хранится как, например:
    # "Agrobiologik asoslar → Botanika".
    # Поэтому ищем название раздела как подстроку.
    variants = {
        decoded_name,
        decoded_name.replace('‘', "'").replace('’', "'").replace('ʻ', "'").replace('ʼ', "'"),
        decoded_name.replace("'", '‘'),
        decoded_name.replace("'", '’'),
        decoded_name.replace("'", 'ʻ'),
        decoded_name.replace("'", 'ʼ'),
    }
    variants = [v for v in variants if v]

    if not variants:
        words = []
    else:
        area_conditions = [
            Word.usage_areas.any(WordUsageArea.area.ilike(f'%{variant}%'))
            for variant in variants
        ]
        words = Word.query.filter(
            or_(*area_conditions),
            ~Word.word.startswith('_category_placeholder_')
        ).order_by(Word.word).all()

    return render_template(
        'field_page.html',
        field_name=decoded_name,
        words=words
    )


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

        # Реальные данные по категориям/частям речи из текущей БД.
        # Никаких фиксированных чисел: статистика пересчитывается при каждом запросе.
        raw_categories = (
            db.session.query(WordCategory.category, func.count(WordCategory.id).label('count'))
            .join(Word, Word.id == WordCategory.word_id)
            .filter(~Word.word.startswith('_category_placeholder_'))
            .filter(WordCategory.category.isnot(None))
            .filter(WordCategory.category != '')
            .group_by(WordCategory.category)
            .all()
        )

        # Нормализуем близкие варианты, которые приходят из JSON:
        # "ot", "ot (birikma)", "fe’l", "sifat/ot" и т.п.
        normalized_counts = {}

        def normalize_category_name(name):
            value = (name or '').strip().lower()
            value = value.replace('’', "'").replace('‘', "'").replace('ʻ', "'").replace('ʼ', "'")

            if not value:
                return None
            if 'sifat' in value and 'ot' in value:
                return "Sifat/ot shaklidagi terminlar"
            if 'birikma' in value or 'birikmali' in value:
                return "Birikmali terminlar"
            if value in {"fe'l", 'fel'} or value.startswith("fe'l ") or value.startswith('fel '):
                return "Fe'l"
            if value == 'sifat' or value.startswith('sifat '):
                return 'Sifat'
            if value == 'ot' or value.startswith('ot '):
                return 'Ot'

            # Для неизвестных/других категорий оставляем исходное название.
            return name.strip()

        for category_name, count in raw_categories:
            display_name = normalize_category_name(category_name)
            if not display_name:
                continue
            normalized_counts[display_name] = normalized_counts.get(display_name, 0) + int(count or 0)

        top_categories = [
            {"name": name, "count": count}
            for name, count in sorted(
                normalized_counts.items(),
                key=lambda item: (-item[1], item[0].lower())
            )[:5]
        ]

        if not top_categories:
            top_categories = [{"name": "Ma'lumot yo'q", "count": 0}]

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

    authenticated = bool(getattr(current_user, 'is_authenticated', False))
    return dict(
        site_lang=session.get('site_lang', 'uz'),
        dictionary_direction=session.get('dictionary_direction', ''),
        session_language_explicit=('site_lang' in session),
        is_admin=authenticated and bool(getattr(current_user, 'is_admin', False)),
        total_words=total_words,
        total_categories=total_categories,
        total_synonyms=total_synonyms,
        database_persistent=app.config.get('DATABASE_IS_PERSISTENT', False),
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
    db.session.rollback()
    app.logger.exception('Internal server error: %s', e)
    return render_template('500.html'), 500


@app.template_filter('numberformat')
def numberformat_filter(value):
    try:
        return f"{int(value):,}".replace(",", " ")
    except (ValueError, TypeError):
        return value



if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)
