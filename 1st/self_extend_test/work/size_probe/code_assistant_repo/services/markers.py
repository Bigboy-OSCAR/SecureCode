def derive_rotation_marker(region: str, shard_id: int) -> str:
    normalized = region.strip().upper()
    shard = f"{shard_id:04d}"
    return f"ROTATE::{normalized}::{shard}"


def derive_rotation_marker_buggy(region: str, shard_id: int) -> str:
    normalized = region.strip().upper()
    shard = f"{shard_id:04d}".lstrip("0")
    return f"ROTATE::{normalized}::{shard}"
