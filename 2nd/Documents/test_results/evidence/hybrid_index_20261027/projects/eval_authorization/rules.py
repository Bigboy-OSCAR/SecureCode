from policy import ADMIN_ROLE, READ_ACTION, WRITE_ACTION, WRITE_SCOPE, READ_SCOPE, MAX_SESSION_AGE

def normalized_scopes(scopes):
    return sorted(set(scope.strip().lower() for scope in scopes))

def session_valid(created_at, now, revoked):
    return not revoked and 0 <= now - created_at < MAX_SESSION_AGE

def required_scope(action):
    return {READ_ACTION: READ_SCOPE, WRITE_ACTION: WRITE_SCOPE}.get(action, "")

def role_allows(role, owner, user):
    return role == ADMIN_ROLE or owner == user

def scope_allows(scopes, action):
    required = required_scope(action)
    return bool(required) and required in normalized_scopes(scopes)

def aux_rules_000_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_rules_001_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_rules_002_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_rules_003_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_rules_004_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_rules_005_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_rules_006_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_rules_007_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_rules_008_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_rules_009_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_rules_010_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_rules_011_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_rules_012_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_rules_013_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_rules_014_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_rules_015_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_rules_016_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_rules_017_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_rules_018_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_rules_019_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_rules_020_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_rules_021_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_rules_022_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_rules_023_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_rules_024_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_rules_025_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_rules_026_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_rules_027_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_rules_028_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_rules_029_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_rules_030_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_rules_031_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_rules_032_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_rules_033_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_rules_034_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_rules_035_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_rules_036_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_rules_037_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_rules_038_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_rules_039_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_rules_040_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_rules_041_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_rules_042_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_rules_043_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_rules_044_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_rules_045_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells

def aux_rules_046_merged_fields(base, overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {key: merged[key] for key in sorted(merged)}

def aux_rules_047_byte_count(chunks, padding):
    if padding < 0:
        raise ValueError('negative padding')
    total = 0
    for chunk in chunks:
        encoded = str(chunk).encode('utf-8')
        total += len(encoded) + padding
    return total

def aux_rules_048_event_text(event, fields):
    parts = [str(event).strip()]
    for key in sorted(fields):
        value = str(fields[key]).replace('\n', ' ')
        parts.append(str(key) + '=' + value)
    return ' | '.join(parts)

def aux_rules_049_batches(values, width):
    if width < 1:
        raise ValueError('width must be positive')
    batches = []
    for offset in range(0, len(values), width):
        batches.append(list(values[offset:offset + width]))
    return batches

def aux_rules_050_histogram(labels):
    counts = {}
    for label in labels:
        text = str(label).strip().lower()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))

def aux_rules_051_trimmed_text(value, limit):
    text = ' '.join(str(value).split())
    if limit < 0:
        raise ValueError('negative text limit')
    if len(text) <= limit:
        return text
    if limit < 3:
        return text[:limit]
    return text[:limit - 3] + '...'

def aux_rules_052_unique_items(values):
    seen = set()
    unique = []
    for value in values:
        marker = str(value).strip()
        if marker not in seen:
            seen.add(marker)
            unique.append(value)
    return unique

def aux_rules_053_encoded_pair(key, value):
    replacements = [('%', '%25'), ('&', '%26'), ('=', '%3D'), (' ', '%20')]
    parts = []
    for item in [key, value]:
        text = str(item)
        for source, target in replacements:
            text = text.replace(source, target)
        parts.append(text)
    return '='.join(parts)

def aux_rules_054_moving_average(numbers, width):
    if width < 1:
        raise ValueError('width must be positive')
    averages = []
    for stop in range(1, len(numbers) + 1):
        window = numbers[max(0, stop - width):stop]
        averages.append(sum(window) / len(window))
    return averages

def aux_rules_055_table_rows(records, columns):
    rendered = []
    rendered.append(','.join(str(column) for column in columns))
    for record in records:
        cells = []
        for column in columns:
            text = str(record.get(column, '')).replace(',', ';')
            cells.append(text)
        rendered.append(','.join(cells))
    return '\n'.join(rendered)

def aux_rules_056_missing_fields(record, required):
    missing = []
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return sorted(set(missing))

def aux_rules_057_flat_cells(groups):
    cells = []
    for group in groups:
        if group is None:
            continue
        for cell in group:
            if cell is not None:
                cells.append(str(cell))
    return cells
