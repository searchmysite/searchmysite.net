from flask import Flask, Blueprint, request, url_for
import os
#from flask_restx import Api
from logging.config import dictConfig

from searchmysite.adminutils import get_host

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

    # Inject the canonical URL of the current page, so search engines can consolidate
    # duplicates (e.g. /?ref=michael-lewis.com and /?ref=michaelianlewis.com) to the canonical URL (e.g. /)
    # get_host() fixes up the host, which is http://127.0.0.1:8080/ when run behind
    # the production reverse proxy (the proxy sets X-Forwarded-Host)
    # In the case of /search/browse/ there are a small number of params that are allowed 
    # to be passed through to the canonical URL, e.g. https://searchmysite.net/search/browse/?&page=2
    # This is to support the pages listed in sitemap.xml which should be indexable by search engines.
    from searchmysite.adminutils import get_host
    @app.context_processor
    def inject_canonical():
        if request.endpoint:
            url = url_for(request.endpoint, **request.view_args, _external=True)
            canonical_url = get_host(url, request.headers)
            params = request.args.to_dict(flat=True)
            if request.endpoint == 'search.browse':
                sort = ''
                if 'sort' in params:
                    sort = 'sort={}'.format(str(params['sort']).replace(' ', '+')) # e.g. change "date_domain_added asc" to "date_domain_added+asc"
                owner_verified = ''
                if 'owner_verified' in params:
                    owner_verified = 'owner_verified={}'.format(params['owner_verified'])
                page = ''
                if 'page' in params and params['page'] != '1': # only include page param if it's not the first page
                    page = 'page={}'.format(params['page'])
                params_for_canonical = '&'.join(filter(None, [sort, owner_verified, page]))
                if params_for_canonical:
                    canonical_url += '?' + params_for_canonical
            return { 'canonical_url': canonical_url }
        return {'canonical_url': None}

    # All /admin pages are for site owners, not search engines, so mark them noindex
    # (robots.txt no longer disallows /admin, so the meta tag is how they're excluded)
    # Done at app level (rather than blueprint level) because create_app() can be
    # called more than once in a process (e.g. by the tests), and blueprint setup
    # methods can't be called after the blueprint has been registered once
    admin_blueprint_names = {'add', 'admin', 'auth', 'checkout', 'contact', 'manage'}
    @app.context_processor
    def inject_noindex():
        if request.endpoint and request.endpoint.split('.')[0] in admin_blueprint_names:
            return {'noindex': True}
        return {}

    # A custom filter for formatting date strings
    @app.template_filter()
    def datetimeformat(value, format='%d %b %Y, %H:%M%z'):
        if value:
            return value.strftime(format)
        else:
            return ""

    return app
