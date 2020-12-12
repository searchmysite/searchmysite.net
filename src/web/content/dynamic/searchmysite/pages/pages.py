from flask import Flask, request, url_for, render_template, Blueprint
from urllib.request import urlopen
from os import environ
import json

bp = Blueprint('pages', __name__)

@bp.route('/about/')
def about():
    return render_template('pages/about.html')

@bp.route('/documentation/')
def documentation():
    return render_template('pages/documentation.html')

@bp.route('/privacy/')
def privacy():
    return render_template('pages/privacy.html')

@bp.route('/terms/')
def terms():
    return render_template('pages/terms.html')