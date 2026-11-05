"""기존 직접 실행 명령을 인증된 서비스 진입점으로 연결한다."""

import sys

from securecode_context.app.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
