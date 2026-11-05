"""R0 색인과 Source Pointer에서 Windows 파일 핸들의 실제 위치와 변경 시각을 확인한다."""

import sys

if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes
    from pathlib import Path

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _get_path = _kernel.GetFinalPathNameByHandleW
    _get_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    _get_path.restype = wintypes.DWORD

    class _FileBasicInfo(ctypes.Structure):
        """클래스 이름: _FileBasicInfo
        기능: Win32 FILE_BASIC_INFO의 변경 시각과 파일 속성 레이아웃을 표현한다.
        작성 날짜: 2026/11/05
        """

        _fields_ = [
            ("creation_time", ctypes.c_int64),
            ("access_time", ctypes.c_int64),
            ("write_time", ctypes.c_int64),
            ("change_time", ctypes.c_int64),
            ("attributes", wintypes.DWORD),
        ]

    _get_info = _kernel.GetFileInformationByHandleEx
    _get_info.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.POINTER(_FileBasicInfo),
        wintypes.DWORD,
    ]
    _get_info.restype = wintypes.BOOL

    def final_path(fd: int) -> Path:
        """함수 이름: final_path()
        기능: 재분석 지점을 모두 따른 열린 핸들의 실제 DOS/UNC 경로를 읽는다.
        인자: fd -> 읽기 전용 파일 기술자
        반환값: Windows 최종 경로
        작성 날짜: 2026/11/05
        """
        handle = msvcrt.get_osfhandle(fd)
        buffer = ctypes.create_unicode_buffer(32768)
        count = _get_path(handle, buffer, len(buffer), 0)
        if not 0 < count < len(buffer):
            raise PermissionError("cannot verify source handle path")
        name = buffer.value
        if name.startswith("\\\\?\\UNC\\"):
            return Path("\\\\" + name[8:])
        return Path(name.removeprefix("\\\\?\\"))

    def change_time(fd: int) -> int:
        """함수 이름: change_time()
        기능: 파일 생성 시간이 아닌 실제 메타데이터 변경 시각을 핸들에서 읽는다.
        인자: fd -> 파일 기술자
        반환값: FILE_BASIC_INFO.ChangeTime 값
        작성 날짜: 2026/11/05
        """
        info = _FileBasicInfo()
        if not _get_info(msvcrt.get_osfhandle(fd), 0, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError("cannot verify source change time")
        return int(info.change_time)
