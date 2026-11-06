"""작업 공간 스캔, revision 저장·전환, 변경 감지 공개 export(3.4 입력 계약)."""

from .changes import ManifestChanges, RevisionChanges, diff_manifests
from .ports import SourceRegistryPort, UnregisteredSourceRegistry
from .records import IndexRevisionRecord
from .revision_store import RevisionStore, RevisionStoreError
from .roots import RootPolicy
from .scanner import Diagnostic, R0Index, ScanResult, build_index, scan_workspace
from .service import SymbolIndexService
from .verification import VerifiedSymbol

__all__ = [
    "Diagnostic",
    "IndexRevisionRecord",
    "ManifestChanges",
    "R0Index",
    "RevisionChanges",
    "RevisionStore",
    "RevisionStoreError",
    "RootPolicy",
    "ScanResult",
    "SourceRegistryPort",
    "SymbolIndexService",
    "UnregisteredSourceRegistry",
    "VerifiedSymbol",
    "build_index",
    "diff_manifests",
    "scan_workspace",
]
