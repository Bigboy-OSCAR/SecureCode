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

## 부록 · 대화에서 개별 도구의 실행 이력 확인하기

앞의 네 단계에서 사용한 **같은 대화**에서 이어 갑니다. 한 질문의 답변이 끝나면 **이 답변의 작업**을 펼치세요. 각 줄의 한글 이름과 **완료** 표시로 어떤 도구가 실행되었는지 확인할 수 있습니다. **상세 기록**에는 해당 작업의 요약이 있습니다.

아래 질문 중 `POINTER`가 있는 경우에는 보내기 전에 자기 화면의 주소로 바꿉니다. PDF는 **3단계**의 답변, 실행 기록은 **1단계 6번**의 답변으로 스크롤하세요. 각각 **답변에 사용한 근거**에서 `securecode://`부터 `?v=1`까지 복사합니다. 바로 뒤의 공백·가운뎃점(`·`)·revision 표시는 빼세요. 등록을 갱신해서 버전 값이 달라졌다면 화면에 표시된 버전을 그대로 복사합니다. 질문 속 대문자 `POINTER` 자리에 그 주소만 붙여 넣습니다.

### A. 파일 목록 → 검색 → 한 줄 읽기

아래 질문을 보냅니다. 파일을 찾는 범위는 이 프로젝트의 `reference` 폴더이고, 읽을 곳은 장비 설정의 5번째 줄입니다.

```text
Call list_files on reference. Then call search_file for wind_guard in reference/recorder.json and read_file for line 5 only. What wind guard is listed? Answer in Korean if possible.
```

**이 답변의 작업**에 **파일 목록 · 완료**, **파일 검색 · 완료**, **파일 부분 읽기 · 완료**가 보이고, 답에는 **double fleece**가 나옵니다.

### B. PDF 파싱 → 상태 확인 → 검색 → 한 쪽 읽기

`POINTER`를 **3단계에서 수첩 2쪽을 읽은 답변**의 근거 주소로 바꿔 보냅니다.

```text
Use pdf_parse for POINTER. Call pdf_status with its returned job_id. Use pdf_search for "The return cue is". Call pdf_read_pages with only pointer, start_page 2 and end_page 2. Omit cursor. What is the return cue? Answer in Korean if possible.
```

**이 답변의 작업**에서 **PDF 파싱**, **PDF 상태 확인**, **PDF 검색**, **PDF 페이지 읽기** 각각의 **완료**를 확인합니다. 답은 **AMBER REED**, **답변에 사용한 근거**는 **원본 PDF 2쪽**입니다. 위 질문은 처음 읽을 때 이어 읽기 값(`cursor`)을 생략하도록 지정합니다. 검증 때 네 도구가 각각 한 번에 완료됐습니다. 모델이 재시도하면 완료 행과 쪽수 근거를 확인하세요. 본문의 **3. PDF** 절차로 같은 페이지를 직접 열 수도 있습니다.

### C. 실행 기록 검색 → 요약 한 줄 읽기

`POINTER`를 **1단계에서 192개 구간을 확인한 답변**의 근거 주소로 바꿔 보냅니다. 줄 번호와 중괄호 안의 영문은 그대로 둡니다.

```text
Call runtime_search on POINTER for CAPTURE_SUMMARY. Then call runtime_read with the same pointer and selector {"type":"line","start":193,"end":193}. Omit cursor. Report the window count in Korean if possible.
```

**이 답변의 작업**에서 **실행 결과 검색 · 완료**, **실행 결과 부분 읽기 · 완료**를 확인합니다. 답에는 **192개**(`windows=192`), **답변에 사용한 근거**에는 원본 바이트 범위 **10322–10377**이 나옵니다.

### D. R0 코드 검색 → 검색한 함수의 원문 읽기

본문 4단계에서 Fieldnote의 인덱스를 만든 다음 아래 질문을 보냅니다. 모델이 함수명으로 검색하고, 검색 결과에 들어 있는 후보 번호와 인덱스 버전으로 실제 원문을 읽습니다.

```text
Call code_search with query classifyPeak and limit 1. Call code_read using the exact candidate_id and index_revision returned. Which label does the function return at -6 dBFS? Answer in Korean if possible.
```

**이 답변의 작업**에 **R0 코드 검색 · 완료**와 **R0 원문 읽기 · 완료**가 모두 보입니다. 답은 **hot**이며, **답변에 사용한 근거**의 **archive.js:2-8**은 해당 함수가 있는 파일과 줄입니다.

### E. 파일 쓰기 승인 → 저장한 한 줄 확인하기

이 단계에서는 Fieldnote 폴더에 실습용 `review-slip.txt` 한 개를 만듭니다. 처음 배포된 프로젝트에는 이 파일이 없습니다. 같은 이름으로 보관 중인 파일이 있다면 질문 속 파일명을 새 이름으로 바꾸세요.

```text
Use write_file to create review-slip.txt with exactly the text FIELDNOTE REVIEWED. Then use read_file to verify the saved text. Answer in Korean if possible.
```

1. **이 파일 변경을 허용할까요?**가 뜨면 대상이 **write review-slip.txt**이고 내용이 **FIELDNOTE REVIEWED**인지 확인하고 **허용**을 누릅니다. 새 이름을 사용했다면 승인 카드에도 그 이름이 보여야 합니다. 기존 파일을 덮어쓰게 되는 경우에는 **거절**을 누릅니다.
2. **이 답변의 작업**에 **파일 쓰기 · 완료**, **파일 부분 읽기 · 완료**가 차례로 보이고, 답에는 방금 저장한 **FIELDNOTE REVIEWED**가 나옵니다. **답변에 사용한 근거**의 원본 범위는 **byte 0–18**입니다. Finder에서 Fieldnote 폴더의 실습 파일을 열어 한 줄을 직접 대조할 수 있습니다.

## 시연 검증 기록

2026년 11월 15일 이 Mac의 Local Desk에서 **Qwen 2.5 · 7B**를 선택하고 본문과 부록의 질문을 전송했습니다. 최종 프로젝트의 인덱스는 **발견 10 · 색인 3 · 제외 7 · 실패 0**이었습니다. 본문 네 단계의 답변에서 각각 실행 로그의 193번째 줄, 설정 파일의 5번째 줄, PDF 2쪽, `archive.js`의 2–8번째 줄을 근거와 대조했습니다. 부록까지 포함해 서로 다른 도구 13개의 **완료** 행을 확인했습니다. 같은 질문도 답변의 문장이나 작업 횟수는 달라질 수 있으니, 시연에서는 각 단계에 적힌 값과 출처를 확인하세요.
