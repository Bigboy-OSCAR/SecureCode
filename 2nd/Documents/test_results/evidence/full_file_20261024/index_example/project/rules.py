from policy import SAFETY_STOCK

def sellable(on_hand, held):
    return max(0, on_hand - held - SAFETY_STOCK)
