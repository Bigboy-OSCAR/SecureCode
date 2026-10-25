from policy import STEP_GRAMS, STEP_CENTS, FREE_FROM_CENTS, MAX_GRAMS, MIN_GRAMS

def weight_steps(grams):
    return (max(grams, MIN_GRAMS) + STEP_GRAMS - 1) // STEP_GRAMS

def weight_charge(grams):
    return weight_steps(grams) * STEP_CENTS

def free_shipping(order_cents):
    return order_cents >= FREE_FROM_CENTS

def allowed_weight(grams):
    return MIN_GRAMS <= grams <= MAX_GRAMS
