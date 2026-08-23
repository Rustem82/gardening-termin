from app import app
from data_sync import sync_dataset

with app.app_context():
    print(sync_dataset(app, force=True))
