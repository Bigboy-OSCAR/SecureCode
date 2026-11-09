"""등록된 Source의 읽기 상한과 조회 중 변경 검사를 담당한다."""

import json
from typing import Any

from securecode_context.pointers.source.registry import SourceRegistry

MAX_LINE_BYTES = 65_536
MAX_TOTAL_BYTES = 16_384
MAX_SCAN_BYTES = 1_048_576
MAX_JSON_BYTES = 8 * 1_048_576


class BoundedSourceReader:
    """클래스 이름: BoundedSourceReader
    기능: 등록된 파일을 제한된 메모리로 읽고 조회 전후 revision을 확인한다.
    작성 날짜: 2026/11/09
    """

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        """함수 이름: __init__()
        기능: 조회 권한과 revision을 검증할 등록부를 보관한다.
        인자: registry -> Source 등록부
        반환값: 없음
        작성 날짜: 2026/11/09
        """
        self.registry = registry

    def _path(self, pointer: str) -> str:
        """함수 이름: _path()
        기능: 등록부의 경로 검증을 통과한 파일만 반환한다.
        인자: pointer -> 등록된 포인터
        반환값: 검증된 원본 경로
        작성 날짜: 2026/11/09
        """
        if not isinstance(self.registry, SourceRegistry):
            raise ValueError("WORKSPACE_ESCAPE_FORBIDDEN: Source registry is required")
        descriptor = self.registry.stat(pointer)
        return self.registry.validate_path(
            descriptor.workspace_id, descriptor.real_path, allow_external=True
        )

    def read_range(
        self,
        pointer: str,
        start_line: int = 1,
        end_line: int = 100,
        max_bytes: int = MAX_TOTAL_BYTES,
    ) -> dict[str, Any]:
        """함수 이름: read_range()
        기능: 줄을 제한된 크기로 읽고 반환 전 원본 변경 여부를 재검증한다.
        인자: pointer -> 등록된 포인터, start_line/end_line -> 포함 범위, max_bytes -> 응답 상한
        반환값: 내용과 실제 읽은 바이트 수, 잘림 상태
        작성 날짜: 2026/11/09
        """
        if start_line < 1 or end_line < start_line or not 1 <= max_bytes <= MAX_TOTAL_BYTES:
            raise ValueError("INVALID_SELECTOR: Invalid line range or byte cap")
        file_path = self._path(pointer)
        lines: list[str] = []
        scanned = 0
        output_bytes = 0
        truncated = False
        with open(file_path, "rb") as stream:
            for line_number in range(1, end_line + 1):
                raw_line = stream.readline(min(MAX_LINE_BYTES, MAX_SCAN_BYTES - scanned) + 1)
                if not raw_line:
                    break
                scanned += len(raw_line)
                if scanned > MAX_SCAN_BYTES or len(raw_line) > MAX_LINE_BYTES:
                    raise ValueError("INVALID_SELECTOR: Line or scan cap exceeded")
                if line_number < start_line:
                    continue
                if output_bytes + len(raw_line) > max_bytes:
                    truncated = True
                    break
                output_bytes += len(raw_line)
                lines.append(raw_line.decode("utf-8", errors="strict").rstrip("\r\n"))
        self._path(pointer)
        return {
            "pointer": pointer,
            "lines": lines,
            "content": "\n".join(lines),
            "bytes_read": scanned,
            "truncated": truncated,
        }

    def read_json_path(self, pointer: str, json_path: str | None = None) -> Any:
        """함수 이름: read_json_path()
        기능: 등록된 JSON만 크기 상한 안에서 파싱하고 작은 결과만 반환한다.
        인자: pointer -> 등록된 포인터, json_path -> 단순 점 구분 키 경로
        반환값: 선택된 JSON 값
        작성 날짜: 2026/11/09
        """
        file_path = self._path(pointer)
        with open(file_path, "rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("PAYLOAD_TOO_LARGE: JSON input exceeds 8 MiB")
        current: Any = json.loads(raw)
        if json_path and json_path != "$":
            if not json_path.startswith("$."):
                raise ValueError("INVALID_SELECTOR: Expected $.key path")
            for key in json_path[2:].split("."):
                if not key or not isinstance(current, dict) or key not in current:
                    current = None
                    break
                current = current[key]
        if len(json.dumps(current, ensure_ascii=False).encode("utf-8")) > MAX_TOTAL_BYTES:
            raise ValueError("PAYLOAD_TOO_LARGE: JSON result exceeds read cap")
        self._path(pointer)
        return current


SourceReader = BoundedSourceReader
