from policy import OPEN_MINUTE, CLOSE_MINUTE, SLOT_MINUTES, UNAVAILABLE
from rules import round_slot, working_day, valid_duration, overlaps

def first_available(day, earliest, duration, busy):
    if not working_day(day) or not valid_duration(duration):
        return UNAVAILABLE
    start = round_slot(max(earliest, OPEN_MINUTE))
    while start + duration <= CLOSE_MINUTE:
        if not overlaps(start, start + duration, busy):
            return start
        start += SLOT_MINUTES
    return UNAVAILABLE

def appointment(day, earliest, duration, busy):
    start = first_available(day, earliest, duration, busy)
    return {"day": day, "start": start, "end": start + duration if start >= 0 else UNAVAILABLE}

def weekday_label(day):
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[day % 7]
