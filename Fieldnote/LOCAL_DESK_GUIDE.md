# Fieldnote로 따라 하는 Local Desk 시연

현장 소리 도감의 장비 점검을 실행하고, 실행 결과 한 줄·장비 설정 한 줄·현장 수첩 한 쪽을 골라 모델에게 물어봅니다. 마지막에는 도감 화면에 **레벨 주의**가 붙는 이유를 원본 코드에서 찾습니다.

## 준비 · 프로젝트와 모델 선택

1. Finder에서 `⌘⇧G`를 누르고 `/Users/oscar/Desktop/SecureCode/2nd/Project/dist`를 입력한 뒤 Return을 누릅니다. **LocalDesk.app**을 엽니다. 웹 도감은 독립적으로 실행되므로 이 시연 중에는 닫아 두어도 됩니다.
2. 왼쪽의 **+ 프로젝트 추가**를 누릅니다. **프로젝트 폴더**에 `/Users/oscar/Desktop/SecureCode/Fieldnote`를 붙여 넣고 **프로젝트 이름**이 `Fieldnote`인지 확인한 뒤 **프로젝트 만들기**를 누릅니다. 이미 등록했다면 왼쪽 목록의 **Fieldnote**를 선택합니다.
3. 대화 화면 오른쪽 위에서 현재 모델 이름을 누릅니다. **로컬 모델 변경** 창의 **Qwen 2.5 · 7B** 행을 눌러 불러옵니다. **사용 중**이 뜨면 창을 닫고 상단에 **Qwen 2.5 · 7B 실행 중**이 표시되는지 확인합니다.
4. 방금 만든 프로젝트는 **새 대화** 화면에서 바로 시작합니다. 기존 프로젝트에 새 대화를 만들 때는 왼쪽 **Fieldnote** 행에 마우스를 올리고 오른쪽의 새 대화 버튼을 누릅니다. 아래 실습은 같은 대화에서 진행합니다. 실행 결과는 생성한 대화에 속합니다. 인덱스는 마지막 단계에서 생성하거나 갱신합니다.

아래 영어 문장은 **대화 입력창**에 복사하고 Return으로 보냅니다. **자료 · 컨텍스트**는 대화 화면 위쪽에 있습니다. 누르면 오른쪽 패널이 열립니다. 필요한 항목까지 그 패널 안을 스크롤하고, 질문을 보낼 때는 패널 상단의 **닫기**를 누릅니다.

## 1. Runtime Pointer · 장비 점검 결과에서 마지막 한 줄 찾기

1. 대화 입력창에 다음 문장을 보냅니다.

   ```text
   Use run_command to execute exactly `python3 capture_report.py` once in this project. When the command finishes, confirm in one sentence. Answer in Korean if possible.
   ```

2. **이 작업을 실행할까요?** 카드에서 명령이 `python3 capture_report.py`인지 확인하고 **허용**을 누릅니다. 완료 뒤 **이 답변의 작업**을 펼치면 명령 실행과 출력 크기 **10,378 bytes**를 확인할 수 있습니다.
3. **자료 · 컨텍스트**를 열고 **Source · Runtime Pointer**까지 내립니다. **Runtime**을 누르고 **현재 세션의 Runtime Pointer**에서 방금 생성된 항목의 동그라미를 선택합니다. 목록이 비어 있으면 **Runtime 목록 새로고침**을 누릅니다. 시연 시 저장 항목 크기는 **10,405 bytes**였습니다.
4. 아래 **Source · Runtime 부분 읽기와 검색**의 **포인터 내용 검색**에 `CAPTURE_SUMMARY`를 입력하고 **포인터 검색**을 누릅니다. **줄 193**에서 `CAPTURE_SUMMARY windows=192 loudest_dbfs=-3 kit=Reed-04`가 나옵니다. 검색 결과의 바이트 범위는 **10322–10377**입니다.
5. 같은 영역의 **읽기 범위**를 **줄 범위**로 바꾸고, **시작 줄**과 **끝 범위 (선택)**에 각각 `193`을 입력한 뒤 **범위 읽기**를 누릅니다. 요약 한 줄이 보이면 패널을 닫습니다. 입력창 위에 **선택 자료**가 붙습니다.
6. 다음 문장을 보내고 답변에서 **192개 구간**, **−3 dBFS**를 확인합니다. 답변 아래 **답변에 사용한 근거**에서 방금 읽은 실행 결과의 범위를 대조합니다.

   ```text
   Using only the selected CAPTURE_SUMMARY line, how many windows were measured and what was the loudest peak in dBFS? Answer in Korean if possible.
   ```

## 2. Source Pointer · 장비 설정에서 방풍 커버 이름 읽기

1. **자료 · 컨텍스트 → Source · Runtime Pointer**로 갑니다. **등록할 외부 파일의 호스트 경로**에 아래 경로를 붙여 넣고 **지정한 파일 등록**을 누릅니다.

   ```text
   /Users/oscar/Desktop/SecureCode/Fieldnote/reference/recorder.json
   ```

2. **Source**를 누르고 **등록한 Source**에서 **recorder.json** 옆 동그라미를 선택합니다. **Source · Runtime 부분 읽기와 검색 → 읽기 범위**를 **JSON 경로**로 바꿉니다. **JSON Pointer 경로**에 `/profile/wind_guard`를 입력하고 **범위 읽기**를 누릅니다. 해당 값 **"double fleece"**만 표시됩니다.
3. 경로로 추출한 값은 보기용입니다. 원본 줄을 질문에 첨부하려면 **읽기 범위 → 줄 범위**로 바꿉니다. **시작 줄**과 **끝 범위 (선택)**에 각각 `5`를 넣고 **범위 읽기**를 누릅니다. `"wind_guard": "double fleece"`가 보이면 패널을 닫고 **선택 자료**가 표시되는지 확인합니다.
4. 다음 문장을 보냅니다. 예상 답은 **double fleece**입니다. **답변에 사용한 근거**에서 `source securecode://source/…`와 **원본 byte 66-99**를 확인합니다. 파일 이름과 revision은 오른쪽 패널의 읽기 결과에도 표시됩니다.

   ```text
   From the selected recorder.json line, what is the exact wind_guard value? Keep the English value and answer in Korean if possible.
   ```

## 3. PDF · 현장 수첩 2쪽에서 복귀 신호 찾기

1. **자료 · 컨텍스트 → Source · Runtime Pointer**에서 아래 경로를 **등록할 외부 파일의 호스트 경로**에 붙여 넣고 **지정한 파일 등록**을 누릅니다. **Source → 등록한 Source**에서 **field-guide.pdf**의 동그라미를 선택합니다.

   ```text
   /Users/oscar/Desktop/SecureCode/Fieldnote/reference/field-guide.pdf
   ```

2. 패널을 아래로 내려 **PDF parsing job → PDF parse job 시작**을 누릅니다. **ready · 원본 2쪽**이 보이면 텍스트 추출이 끝난 것입니다.
3. 조금 위쪽의 **Source · Runtime 부분 읽기와 검색 → 포인터 내용 검색**에 `The return cue is`를 입력하고 **포인터 검색**을 누릅니다. **원본 PDF 2쪽**, 바이트 범위 **185–214**에서 해당 문장이 나옵니다.
4. **읽기 범위 → PDF 페이지**를 선택합니다. **시작 페이지**와 **끝 범위 (선택)**에 각각 `2`를 입력하고 **범위 읽기**를 누릅니다. 서비스 출처의 **원본 PDF 2쪽**, 바이트 범위 **0–393**, 본문의 **The return cue is AMBER REED.**를 확인합니다.
5. 패널을 닫고 아래 문장을 보냅니다. 답에 **AMBER REED**가 그대로 있고 **답변에 사용한 근거**가 수첩 2쪽을 가리키는지 봅니다. [현장 수첩](reference/field-guide.pdf)을 열어 두 번째 쪽의 **Return cue**와도 대조할 수 있습니다.

   ```text
   On the selected page of field-guide.pdf, what is the return cue? Keep the two English words exactly as printed. Answer in Korean if possible.
   ```

## 4. R0 인덱스 · 레벨 분류 함수를 찾아 답변과 대조하기

1. 대화 입력창에 **선택 자료**가 남아 있으면 옆의 **×**(**선택 자료 포함 해제**)를 누릅니다.
2. 왼쪽 아래 **인덱스 생성·갱신**을 누릅니다. **프로젝트 선택**에서 **Fieldnote**만 체크하고 **1개 생성·갱신**을 누릅니다. 완료 화면에서 **색인 3**, **실패 0**, **revision** 번호를 확인합니다. 색인 대상은 JavaScript 파일 두 개와 Python 파일 한 개입니다. HTML·CSS·문서 등이 제외되어 **부분 완료**로 표시될 수 있습니다. **닫기**를 누릅니다.
3. **자료 · 컨텍스트**의 맨 위 **R0 원문 · 컨텍스트 예산**에서 **심볼·파일 검색어**에 `classifyPeak`를 입력하고 **원문 심볼 검색**을 누릅니다. 후보 목록의 **classifyPeak · archive.js:2-8**을 선택한 뒤 **선택한 원문 묶음 읽기**를 누릅니다. **Symbol Bundle** 아래에 파일, 줄 범위, revision과 함께 `peakDb >= -6`, `return "hot"`가 표시됩니다.
4. 아래 영어 문장을 패널 안의 **예산을 확인할 실제 질문**에 붙여 넣고 **컨텍스트 미리보기**를 누릅니다. **호스트 컨텍스트 계획**에서 선택된 코드의 위치와 예산을 확인합니다. 미리보기는 질문을 전송하지 않으므로, 패널을 닫고 **대화 입력창**에도 같은 문장을 붙여 넣어 보냅니다.

   ```text
   According to the comment in classifyPeak in archive.js, which English label applies at exactly -6 dBFS? Answer in Korean if possible and quote the label.
   ```

5. 예상 답은 **"hot"**입니다. **답변에 사용한 근거**에서 `archive.js`와 줄 범위를 확인합니다. 웹 도감에서 **물가 → 방파제의 잔물결**을 선택하면 이 규칙이 적용된 **레벨 주의 · -6 dBFS**를 볼 수 있습니다.
