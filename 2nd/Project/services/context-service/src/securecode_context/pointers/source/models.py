"""Source Pointer 데이터 모델 및 DTO 정의.

작성일: 2026-11-07
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SourceDescriptor:
    """Source Pointer 메타데이터 식별자."""
    pointer: str
    kind: str
    workspace_id: str
    revision: str
    media_type: str
    byte_size: int
    preview: str
    available_operations: List[str] = field(default_factory=list)
    real_path: str = ""
    created_at: float = 0.0


@dataclass
class SourceRegistrationRequest:
    """Source 등록 요청 DTO."""
    workspace_id: str
    target_path: str
    media_type: Optional[str] = None
    allow_external: bool = False
