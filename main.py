from time import sleep

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import stripe

SERVICE_ACCOUNT_JSON = 'digital-food-watch-2.json'  # adjust this accordingly for the project you want to deploy for.

"""
PRODUCT_ID = sys.argv[1]  # prod_blablablablabl for Wear OS + watchOS, prod_lablablablabla for Wear OS, prod_ablablablabla for watchOS
COLLECTION = sys.argv[2]  # e.g., example
DOCUMENT = sys.argv[3]  # e.g., Abcdefghijklmnopqrst
EMAIL = sys.argv[4]  # e.g., firstname.lastname@example.com
"""
def generateInvoice(request):
    request_json = request.get_json()

    API_KEY = request_json.get('api_key')
    if (API_KEY != "redacted"):
        sleep(30)
        return '', 403

    PRODUCT_ID = request_json.get('product_id')
    COLLECTION = request_json.get('collection')
    DOCUMENT = request_json.get('document')
    EMAIL = request_json.get('email')

    stripe.api_key = 'sk_live_redacted'

    # Sanity check the customer email (e.g., against a typo) before doing any Firebase adjustments
    customer = stripe.Customer.list(email=EMAIL).data
    if customer:
        customer = customer[0]
        customer_id = customer["id"]
    else:
        emailError = "No customer with email " + EMAIL + " found"
        print(emailError)
        return emailError, 404

    if not firebase_admin._apps:
        # Use a service account.
        cred = credentials.Certificate(SERVICE_ACCOUNT_JSON)
        app = firebase_admin.initialize_app(cred)

    db = firestore.client()

    ref = db.collection(COLLECTION).document(DOCUMENT)
    existing = ref.get().to_dict()
    commission = existing.get("commission")

    payableDue = round(commission["cumulatedOrdersPrice"] * (commission["percentage"] / 100.0), 2)

    print("payableDue: ")
    print(payableDue)

    if payableDue == 0.0:
        nothingToPay = "Nothing to pay - not creating invoice"
        print(nothingToPay)
        return nothingToPay, 200

    # Create the price in Stripe
    price = stripe.Price.create(
        unit_amount=int(payableDue * 100),
        currency=customer.currency,
        product=PRODUCT_ID,
    )

    print("Price created")

    # Reset the Firebase cumulatedOrderPrice for gathering the price in the next month
    ref.update({
        "commission.cumulatedOrdersPrice": 0
    })

    # Create invoice for customer with payable due
    invoice = stripe.Invoice.create(
        customer=customer_id,
        collection_method='send_invoice',
        days_until_due=30,
    )

    # Create an Invoice Item with the Price and Customer you want to charge
    stripe.InvoiceItem.create(
        customer=customer_id,
        price=price,
        invoice=invoice.id
    )

    # Send the Invoice
    stripe.Invoice.send_invoice(invoice.id)
    print("invoice sent")

    # No deletion allowed by Stripe API. Therefore, archive the price instead to show it's not used anymore
    stripe.Price.modify(
        price.id,
        active=False
    )
    print("Price archived")
    return 'Invoice successfully generated', 200
