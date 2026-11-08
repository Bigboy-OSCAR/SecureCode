"""색인할 작업 공간 루트의 허용 정책을 검사한다."""

from pathlib import Path

from securecode_context.common.errors import ErrorCode, ServiceError


def _rejected(reason: str) -> ServiceError:
    """
    함수 이름: _rejected()
    기능: 경로를 노출하지 않는 FORBIDDEN 오류를 만든다.
    인자: reason -> 계약 details.reason 값
    반환값: ServiceError
    작성 날짜: 2026/11/05
    """
    return ServiceError(ErrorCode.FORBIDDEN, "허용되지 않은 경로입니다.", {"reason": reason})


class RootPolicy:
    """
    클래스 이름: RootPolicy
    기능: 루트 자체가 링크·드라이브 최상위·허용 목록 밖이면 거부하고 실제 경로를 돌려준다.
    작성 날짜: 2026/11/05
    """

    def __init__(self, allowed_roots: tuple[Path, ...] = ()) -> None:
        """
        함수 이름: __init__()
        기능: 허용 루트 목록을 실제 경로로 고정한다. 비어 있으면 위치 제한 없이 다른 규칙만 적용한다.
        인자: allowed_roots -> 사용자가 지정한 상위 디렉터리 목록
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.allowed_roots = tuple(root.resolve(strict=True) for root in allowed_roots)

    def resolve(self, root: Path) -> Path:
        """
        함수 이름: resolve()
        기능: 절대 경로의 기존 디렉터리이며 링크·정션이 아닌지 확인한다.
        인자: root -> 등록 요청 경로
        반환값: 검사한 실제 루트
        작성 날짜: 2026/11/05
        """
        if not root.is_absolute():
            raise _rejected("root_not_absolute")
        if root.is_symlink() or root.is_junction():
            raise _rejected("root_is_link")
        try:
            resolved = root.resolve(strict=True)
        except OSError as error:
            raise _rejected("root_not_found") from error
        if not resolved.is_dir():
            raise _rejected("root_not_directory")
        if resolved == Path(resolved.anchor):
            raise _rejected("root_is_filesystem_root")
        if self.allowed_roots and not any(
            resolved.is_relative_to(allowed) for allowed in self.allowed_roots
        ):
            raise _rejected("path_outside_allowed_roots")
        return resolved
