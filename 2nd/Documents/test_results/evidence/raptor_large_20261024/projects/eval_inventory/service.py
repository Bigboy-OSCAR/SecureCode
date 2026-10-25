from policy import RESERVATION_TTL, ACCEPTED, PARTIAL, DENIED
from rules import sellable, valid_quantity, allocate

def aux_service_000_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_service_001_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_service_002_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_service_003_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_service_004_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_service_005_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_service_006_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_service_007_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_service_008_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_service_009_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_service_010_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_service_011_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_service_012_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_service_013_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_service_014_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_service_015_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_service_016_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_service_017_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_service_018_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_service_019_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_service_020_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_service_021_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_service_022_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_service_023_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_service_024_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_service_025_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_service_026_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_service_027_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_service_028_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_service_029_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_service_030_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_service_031_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_service_032_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_service_033_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_service_034_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_service_035_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_service_036_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_service_037_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_service_038_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_service_039_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_service_040_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_service_041_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_service_042_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_service_043_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_service_044_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_service_045_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_service_046_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_service_047_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_service_048_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_service_049_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_service_050_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_service_051_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_service_052_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_service_053_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_service_054_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_service_055_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_service_056_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

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
