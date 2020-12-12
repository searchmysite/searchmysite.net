import psycopg2
from flask import current_app, g

def get_db():
    if 'db' not in g:
        db_name = current_app.config['DB_NAME']
        db_user = current_app.config['DB_USER']
        db_host = current_app.config['DB_HOST']
        db_password = current_app.config['DB_PASSWORD']
        g.db = psycopg2.connect(dbname=db_name, user=db_user, host=db_host, password=db_password)
        # db is a connection object - need to get a cursor object before execute etc.
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_app(app):
    app.teardown_appcontext(close_db)
