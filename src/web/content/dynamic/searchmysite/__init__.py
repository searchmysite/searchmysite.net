from flask import Flask, Blueprint
import os
from flask_restx import Api
from logging.config import dictConfig

def create_app(test_config=None):
    # Configure logging, as per https://flask.palletsprojects.com/en/1.1.x/logging/ (not required for Flask, but required for Apache httpd + mod_wsgi)
    dictConfig({
        'version': 1,
        'formatters': {'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }},
        'handlers': {'wsgi': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default'
        }},
        'root': {
            'level': 'INFO',
            'handlers': ['wsgi']
        }
    })

    # Work out the app root path, and from there set the template and static folders 
    # In Apache httpd + mod_wsgi, PYTHONPATH should be set to /usr/local/apache2/htdocs/dynamic/
    # In Flask, FLASK_APP should be set to ~/projects/searchmysite/src/web/dynamic/searchmysite
    pythonpath = os.environ.get('PYTHONPATH')
    flask_app = os.environ.get('FLASK_APP')
    if pythonpath: app_root = pythonpath
    elif flask_app: app_root = flask_app
    template_dir = os.path.join(app_root, __name__, 'templates') 
    if not os.path.exists(template_dir): template_dir = os.path.join(app_root, 'templates')
    static_dir = os.path.join(app_root, '../static')
    if not os.path.exists(static_dir): static_dir = os.path.join(app_root, '../../static')
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.logger.debug('app_root: {}, template_dir: {}, static_dir {}'.format(app_root, template_dir, static_dir))

    # Load the config, either default or a test config if passed in
    config_file = os.path.join(app.root_path, '../config.py')
    if test_config is None:
        app.config.from_pyfile(config_file, silent=True)
    else:
        app.config.from_mapping(test_config)

    # Initialise database
    from searchmysite import db
    db.init_app(app)

    # Get url prefixes
    # Apache httpd + mod_wsgi has the config:
    # WSGIScriptAlias /api /usr/local/apache2/htdocs/dynamic/searchmysite.wsgi
    # WSGIScriptAlias /admin /usr/local/apache2/htdocs/dynamic/searchmysite.wsgi
    # WSGIScriptAlias /pages /usr/local/apache2/htdocs/dynamic/searchmysite.wsgi
    # WSGIScriptAlias /search /usr/local/apache2/htdocs/dynamic/searchmysite.wsgi
    # So we need to set up explicit url prefixes in Flask to match these urls
    api_url_prefix, admin_url_prefix, pages_url_prefix, search_url_prefix = '/v1', '/', '/', '/'
    if flask_app:
        api_url_prefix = '/api/v1'
        admin_url_prefix = '/admin'
        pages_url_prefix = '/pages'
        search_url_prefix = '/search'

    # Register blueprints
    # **IMPORTANT**: all @bp.route URLs in the blueprints below must be unique.
    # If there are duplicates, e.g. 2 blueprints with @bp.route('/'), only the first will be used 
    # and the other will silently fail, due to the web server config above
    # /api    
    from searchmysite.api import searchapi
    app.register_blueprint(searchapi.bp, url_prefix=api_url_prefix)
    # /admin
    from searchmysite.admin import add
    app.register_blueprint(add.bp, url_prefix=admin_url_prefix)
    from searchmysite.admin import admin
    app.register_blueprint(admin.bp, url_prefix=admin_url_prefix)
    from searchmysite.admin import auth
    app.register_blueprint(auth.bp, url_prefix=admin_url_prefix)
    from searchmysite.admin import checkout
    app.register_blueprint(checkout.bp, url_prefix=admin_url_prefix)
    from searchmysite.admin import contact
    app.register_blueprint(contact.bp, url_prefix=admin_url_prefix)
    from searchmysite.admin import manage
    app.register_blueprint(manage.bp, url_prefix=admin_url_prefix)
    # /pages
    from searchmysite.pages import pages
    app.register_blueprint(pages.bp, url_prefix=pages_url_prefix)
    # /search
    from searchmysite.search import search
    app.register_blueprint(search.bp, url_prefix=search_url_prefix)

    # A custom filter for formatting date strings
    @app.template_filter()
    def datetimeformat(value, format='%d %b %Y, %H:%M%z'):
        if value:
            return value.strftime(format)
        else:
            return ""

    return app
