from policy import RESERVATION_TTL, ACCEPTED, PARTIAL, DENIED
from rules import sellable, valid_quantity, allocate

def reserve(on_hand, held, requested, allow_partial, now):
    if not valid_quantity(requested):
        return {"status": DENIED, "units": 0, "expires": now}
    units = allocate(sellable(on_hand, held), requested, allow_partial)
    status = ACCEPTED if units == requested else PARTIAL if units else DENIED
    return {"status": status, "units": units, "expires": now + RESERVATION_TTL if units else now}

def remaining_after(on_hand, held, requested, allow_partial):
    reservation = reserve(on_hand, held, requested, allow_partial, 0)
    return sellable(on_hand, held + reservation["units"])

def stock_label(on_hand):
    return "empty" if on_hand <= 0 else "stocked"
