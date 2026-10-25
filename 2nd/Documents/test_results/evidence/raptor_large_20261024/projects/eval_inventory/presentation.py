def aux_presentation_000_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_presentation_001_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_presentation_002_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_presentation_003_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_presentation_004_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_presentation_005_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_presentation_006_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_presentation_007_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_presentation_008_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_presentation_009_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_presentation_010_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_presentation_011_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_presentation_012_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_presentation_013_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_presentation_014_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_presentation_015_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_presentation_016_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_presentation_017_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_presentation_018_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_presentation_019_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_presentation_020_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_presentation_021_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_presentation_022_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_presentation_023_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_presentation_024_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_presentation_025_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_presentation_026_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_presentation_027_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_presentation_028_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_presentation_029_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_presentation_030_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_presentation_031_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_presentation_032_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_presentation_033_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_presentation_034_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_presentation_035_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_presentation_036_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_presentation_037_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_presentation_038_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_presentation_039_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_presentation_040_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_presentation_041_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_presentation_042_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_presentation_043_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_presentation_044_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_presentation_045_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_presentation_046_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_presentation_047_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_presentation_048_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_presentation_049_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_presentation_050_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_presentation_051_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_presentation_052_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_presentation_053_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_presentation_054_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_presentation_055_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_presentation_056_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_presentation_057_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

DISPLAY_PREFIX = "warehouse"
DISPLAY_WIDTH = 12
UNKNOWN_LABEL = "unknown"
MAX_LABEL_LENGTH = 48

def normalize_label(label):
    return label.strip().lower().replace(" ", "-")[:MAX_LABEL_LENGTH]

def display_reference(reference):
    return DISPLAY_PREFIX + ":" + str(reference).zfill(DISPLAY_WIDTH)

def status_label(code):
    return {0: "pending", 1: "ready", 2: "closed"}.get(code, UNKNOWN_LABEL)

def summarize_count(values):
    return {"domain": DISPLAY_PREFIX, "count": len(values)}
