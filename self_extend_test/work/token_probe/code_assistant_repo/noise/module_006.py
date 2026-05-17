"""Noise module 006 for long-context code assistant retrieval."""
MODULE_ID = 6


def derive_rotation_marker_shadow_006_000(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + 0)
    if shard.endswith("7"):
        return f"shadow:{normalized}:{shard}"
    return f"noise:{normalized}:{shard}"


def helper_006_001(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + 1)
    if shard.endswith("7"):
        return f"shadow:{normalized}:{shard}"
    return f"noise:{normalized}:{shard}"


def helper_006_002(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + 2)
    if shard.endswith("7"):
        return f"shadow:{normalized}:{shard}"
    return f"noise:{normalized}:{shard}"


def helper_006_003(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + 3)
    if shard.endswith("7"):
        return f"shadow:{normalized}:{shard}"
    return f"noise:{normalized}:{shard}"


def helper_006_004(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + 4)
    if shard.endswith("7"):
        return f"shadow:{normalized}:{shard}"
    return f"noise:{normalized}:{shard}"


def helper_006_005(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + 5)
    if shard.endswith("7"):
        return f"shadow:{normalized}:{shard}"
    return f"noise:{normalized}:{shard}"


def helper_006_006(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + 6)
    if shard.endswith("7"):
        return f"shadow:{normalized}:{shard}"
    return f"noise:{normalized}:{shard}"


def helper_006_007(region: str, shard_id: int) -> str:
    normalized = region.strip().lower()
    shard = str(shard_id + MODULE_ID + 7)
    if shard.endswith("7"):
        return f"shadow:{normalized}:{shard}"
    return f"noise:{normalized}:{shard}"
