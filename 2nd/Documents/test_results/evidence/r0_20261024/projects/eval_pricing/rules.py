from policy import MEMBER_BPS, TAX_BPS, DISCOUNT_CAP_CENTS, MIN_QUANTITY, MAX_QUANTITY

def line_subtotal(unit_cents, quantity):
    if unit_cents < 0 or not MIN_QUANTITY <= quantity <= MAX_QUANTITY:
        return -1
    return unit_cents * quantity

def member_discount(subtotal, member):
    return min(subtotal * MEMBER_BPS // 10000, DISCOUNT_CAP_CENTS) if member else 0

def sales_tax(net_cents):
    return (net_cents * TAX_BPS + 5000) // 10000

def refundable(net_cents, returned_units, total_units):
    return net_cents * min(returned_units, total_units) // total_units
