from flask import (
    Blueprint, render_template, request, url_for, current_app, jsonify
)
from os import environ
from searchmysite.util import get_host
import stripe

bp = Blueprint('checkout', __name__)


# Routes

@bp.route('/checkout/config/', methods=['GET'])
def get_publishable_key():
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    price = stripe.Price.retrieve(current_app.config['STRIPE_PRODUCT_ID'])
    stripe_config = {
        'publicKey': current_app.config['STRIPE_PUBLISHABLE_KEY'],
    }
    return jsonify(stripe_config)

@bp.route("/checkout/create-addsite-checkout-session/")
def create_addsite_checkout_session():
    json = create_checkout_session(url_for('add.success'))
    return json

@bp.route("/checkout/create-subsrenewal-checkout-session/")
def create_subsrenewal_checkout_session():
    json = create_checkout_session(url_for('manage.renew_subscription_success'))
    return json

@bp.route('/checkout/cancelled/')
def checkout_cancelled():
    return render_template('admin/checkout-cancelled.html')

@bp.route("/checkout/webhook/", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config['STRIPE_ENDPOINT_SECRET']
        )
    except ValueError as e:
        # Invalid payload
        current_app.logger.error('Invalid payload.')
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        current_app.logger.error('Invalid signature.')
        return "Invalid signature", 400
    # Handle the checkout.session.completed event
    if event["type"] == "checkout.session.completed":
        current_app.logger.info('Payment was successful.')
    return "Success", 200


# Utilities

def create_checkout_session(success_url_for):
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    domain_url = get_host(request.host_url, request.headers)
    domain_url = domain_url.rstrip('/')
    try:
        # Create new Checkout Session for the order
        # Other optional params include:
        # [billing_address_collection] - to display billing address details on the page
        # [customer] - if you have an existing Stripe Customer ID
        # [payment_intent_data] - capture the payment later
        # [customer_email] - prefill the email input in the form
        # For full details see https://stripe.com/docs/api/checkout/sessions/create
        # ?session_id={CHECKOUT_SESSION_ID} means the redirect will have the session ID set as a query param
        checkout_session = stripe.checkout.Session.create(
            success_url = domain_url + success_url_for + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url = domain_url + url_for('checkout.checkout_cancelled'),
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price": current_app.config['STRIPE_PRODUCT_ID'],
                    "quantity": 1
                }
            ]
        )
        current_app.logger.debug('success_url: {}'.format(checkout_session.get('success_url')))
        return jsonify({"sessionId": checkout_session["id"]})
    except Exception as e:
        return jsonify(error=str(e)), 403
