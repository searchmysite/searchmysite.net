from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from os import environ
from searchmysite.adminutils import send_email

bp = Blueprint('contact', __name__)

@bp.route('/contact/', methods=('GET', 'POST'))
def contact():
    if request.method == 'GET':
        return render_template('admin/contact.html')
    else:
        name = request.form.get('name')
        email = request.form.get('email')
        reason = request.form.get('reason')
        info = request.form.get('additional-info')
        if not email:
            message = 'Please enter your email address.'
            flash(message)
            return render_template('admin/contact.html')
        else:
            subject = "Email from searchmysite.net"
            text = 'Name: {}\n'.format(name)
            text += 'Email: {}\n'.format(email)
            text += 'Reason: {}\n'.format(reason)
            text += 'Additional information: {}'.format(info)
            success_status = send_email(email, None, subject, text)
            if success_status:
                return render_template('admin/success.html', title="Contact Success", message="<p>Thank you for your question/comment. I hope to get back to you shortly.</p>")
            else:
                message = 'Error, message not sent.'
                flash(message)
                return render_template('admin/contact.html')
