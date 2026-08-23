import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-vercel')

    _database_url = os.environ.get('DATABASE_URL', '').strip()
    if _database_url.startswith('postgres://'):
        _database_url = _database_url.replace('postgres://', 'postgresql://', 1)

    if _database_url:
        SQLALCHEMY_DATABASE_URI = _database_url
        DATABASE_IS_PERSISTENT = True
    elif os.environ.get('VERCEL'):
        # Vercel serverless only allows reliable writes under /tmp. This keeps the
        # public site working even before PostgreSQL is configured, but admin edits
        # are not durable until DATABASE_URL is set.
        SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/thesaurus_data.db'
        DATABASE_IS_PERSISTENT = False
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///thesaurus_data.db'
        DATABASE_IS_PERSISTENT = True

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
    DEBUG = False
    TESTING = False

    DATASET_VERSION = os.environ.get('DATASET_VERSION', '2026-08-23-v3')
    AUTO_SYNC_DATA = os.environ.get('AUTO_SYNC_DATA', '0') == '1'
