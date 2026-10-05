from services.markers import derive_rotation_marker


def schedule_rotation(region: str, shard_id: int, urgent: bool = False) -> dict[str, str]:
    marker = derive_rotation_marker(region, shard_id)
    tier = "hot" if urgent else "normal"
    return {"marker": marker, "tier": tier}


def schedule_shadow_rotation(region: str, shard_id: int) -> str:
    return f"shadow::{region.lower()}::{shard_id}"
