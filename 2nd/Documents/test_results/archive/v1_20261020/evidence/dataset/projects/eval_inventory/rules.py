from policy import SAFETY_STOCK, MAX_PER_ORDER, MIN_ORDER, BACKORDER_LIMIT

def sellable(on_hand, held):
    return max(on_hand - held - SAFETY_STOCK, 0)

def valid_quantity(quantity):
    return MIN_ORDER <= quantity <= MAX_PER_ORDER

def allocate(available, requested, allow_partial):
    if available >= requested:
        return requested
    return available if allow_partial else 0

def can_backorder(shortfall):
    return 0 < shortfall <= BACKORDER_LIMIT
