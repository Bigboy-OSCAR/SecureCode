AUDIT_VERSION = 2
MAX_RECENT_EVENTS = 20
REDACTION_MARKER = "***"
DEFAULT_ACTOR = "system"

def audit_key(actor, action):
    return str(AUDIT_VERSION) + ":" + actor.strip().lower() + ":" + action

def recent_events(events):
    return events[-MAX_RECENT_EVENTS:]

def redact_identifier(identifier):
    return REDACTION_MARKER + str(identifier)[-4:]

def event_record(action, actor=None):
    return {"actor": actor or DEFAULT_ACTOR, "action": action, "version": AUDIT_VERSION}

def aux_audit_000_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_audit_001_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_audit_002_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_audit_003_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_audit_004_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_audit_005_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_audit_006_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_audit_007_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_audit_008_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_audit_009_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_audit_010_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_audit_011_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_audit_012_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_audit_013_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_audit_014_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_audit_015_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_audit_016_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_audit_017_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_audit_018_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_audit_019_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_audit_020_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_audit_021_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_audit_022_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_audit_023_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_audit_024_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_audit_025_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_audit_026_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_audit_027_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_audit_028_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_audit_029_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_audit_030_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_audit_031_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_audit_032_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_audit_033_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_audit_034_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_audit_035_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_audit_036_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_audit_037_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_audit_038_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_audit_039_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_audit_040_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_audit_041_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_audit_042_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_audit_043_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_audit_044_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_audit_045_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_audit_046_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_audit_047_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_audit_048_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_audit_049_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_audit_050_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_audit_051_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_audit_052_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_audit_053_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_audit_054_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_audit_055_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_audit_056_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_audit_057_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_audit_058_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}
