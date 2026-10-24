from policy import DELIVERY_CENTS, FREE_DELIVERY_CENTS, CURRENCY
from rules import line_subtotal, member_discount, sales_tax

def checkout_total(unit_cents, quantity, member):
    subtotal = line_subtotal(unit_cents, quantity)
    if subtotal < 0:
        return -1
    net = subtotal - member_discount(subtotal, member)
    delivery = 0 if net >= FREE_DELIVERY_CENTS else DELIVERY_CENTS
    return net + sales_tax(net) + delivery

def order_receipt(unit_cents, quantity, member):
    total = checkout_total(unit_cents, quantity, member)
    return {"currency": CURRENCY, "total": total, "accepted": total >= 0}

def reward_points(total_cents):
    return max(total_cents, 0) // 100
