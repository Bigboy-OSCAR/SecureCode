from policy import SLOT_MINUTES, BUFFER_MINUTES, WORK_DAYS, MIN_DURATION, MAX_DURATION

def round_slot(minute):
    return ((minute + SLOT_MINUTES - 1) // SLOT_MINUTES) * SLOT_MINUTES

def working_day(day):
    return day % 7 in WORK_DAYS

def valid_duration(duration):
    return MIN_DURATION <= duration <= MAX_DURATION

def overlaps(start, end, busy):
    return any(start < busy_end + BUFFER_MINUTES and end > busy_start - BUFFER_MINUTES for busy_start, busy_end in busy)
