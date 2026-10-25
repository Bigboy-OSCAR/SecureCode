from rules import sellable

def remaining(on_hand, held):
    return sellable(on_hand, held)

def label(on_hand):
    return 'empty' if on_hand <= 0 else 'stocked'
