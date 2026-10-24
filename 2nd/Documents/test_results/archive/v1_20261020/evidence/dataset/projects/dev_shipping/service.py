from policy import BASE_CENTS, REMOTE_SURCHARGE, TRACKING_PREFIX
from rules import weight_charge, free_shipping, allowed_weight

def shipping_quote(order_cents, grams, remote):
    if not allowed_weight(grams):
        return {"status": "rejected", "cents": 0}
    charge = 0 if free_shipping(order_cents) else BASE_CENTS + weight_charge(grams)
    if remote:
        charge += REMOTE_SURCHARGE
    return {"status": "accepted", "cents": charge}

def parcel_total(order_cents, grams, remote):
    quote = shipping_quote(order_cents, grams, remote)
    return order_cents + quote["cents"] if quote["status"] == "accepted" else -1

def tracking_key(order_id):
    return TRACKING_PREFIX + ":" + order_id.strip().upper()
