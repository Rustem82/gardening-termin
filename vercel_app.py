# vercel_app.py - полностью независимая версия для Vercel
import sys
import os

# Добавляем текущую папку в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
import json

# Создаем приложение
app = Flask(__name__)

# Настройки прямо здесь
app.config['SECRET_KEY'] = 'your-secret-key-for-vercel'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///thesaurus_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Простые роуты для теста
@app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'message': 'Сервер работает на Vercel!',
        'version': '1.0.0'
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/debug')
def debug():
    try:
        files = os.listdir('.')
        return jsonify({
            'files': files[:20],
            'cwd': os.getcwd(),
            'python_path': sys.path[:5]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Экспортируем для Vercel
application = app