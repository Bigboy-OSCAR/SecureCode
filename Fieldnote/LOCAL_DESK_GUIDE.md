# Fieldnote로 따라 하는 Local Desk 시연

현장 녹음 장비를 점검한 뒤 동료에게 결과를 인계한다고 생각해 보세요. **몇 구간을 측정했는지, 어떤 방풍재가 설정되어 있는지, 현장 수첩의 복귀 신호가 무엇인지, 왜 녹음에 주의 표시가 붙는지**를 확인하게 됩니다. 네 답의 근거는 각각 방금 실행한 점검 로그, 장비 설정 파일, PDF의 특정 쪽, 앱의 분류 함수에 있습니다.

실제 화면을 보며 따라 하려면 준비 1장과 실습 9장으로 구성된 [Figma 시각 실습서](https://www.figma.com/design/heEPn2bvlzowpE6vKw3SoL?node-id=3-2) 또는 [A4 세로 인쇄용 PDF](Fieldnote-Local-Desk-A4.pdf)를 여세요.

## 준비 · 프로젝트와 모델 선택

**준비할 환경**은 Fieldnote 폴더에서 명령을 실행하고 같은 폴더의 자료를 읽을 수 있는 Local Desk 대화 한 개입니다.

1. **앱을 엽니다.** Finder에서 `⌘⇧G`를 누르고 `/Users/oscar/Desktop/SecureCode/2nd/Project/dist`를 입력한 뒤 Return을 누릅니다. **LocalDesk.app**을 엽니다. Fieldnote 웹 도감은 마지막에 화면의 레벨 표시를 대조할 때 열어도 됩니다.
2. **작업할 폴더를 연결합니다.** 왼쪽 **+ 프로젝트 추가**에서 **프로젝트 폴더**에 `/Users/oscar/Desktop/SecureCode/Fieldnote`를 붙여 넣습니다. 이름이 **Fieldnote**인지 확인하고 **프로젝트 만들기**를 누릅니다. 이 폴더가 첫 점검 명령의 실행 위치이자 코드 검색 범위입니다. 이미 등록했다면 왼쪽 목록의 **Fieldnote**를 선택합니다.
3. **시연에 사용한 모델을 고릅니다.** 오른쪽 위 모델 이름을 눌러 **로컬 모델 변경 → Qwen 2.5 · 7B**를 선택합니다. **사용 중**이 뜨면 창을 닫고 상단의 **Qwen 2.5 · 7B 실행 중**을 확인합니다.
4. **한 대화에서 끝까지 진행합니다.** 새 프로젝트는 **새 대화** 화면에서 시작합니다. 기존 프로젝트라면 왼쪽 **Fieldnote** 행에 마우스를 올려 오른쪽 새 대화 버튼을 누릅니다. 첫 실습에서 생기는 실행 로그는 그 대화에 속합니다. 같은 대화에 머물러야 부록 C에서도 그 결과를 다시 찾을 수 있습니다.

각 **질문의 뜻** 아래에 있는 영어 문장을 대화 입력창에 붙여 넣고 Return을 누릅니다. 답변은 가능한 경우 한국어로 요청합니다. 상단 **자료 · 컨텍스트**를 누르면 오른쪽 패널이 열립니다. 자료를 고르고 패널 상단 **닫기**를 누르면 대화로 돌아옵니다.

## 1. Runtime Pointer · 장비 점검 결과에서 마지막 한 줄 찾기

**해결할 질문**　“이번 장비 점검에서 몇 구간을 측정했고, 가장 큰 피크는 몇 dBFS였을까?” 점검 프로그램은 가상 측정값을 한 줄씩 출력한 뒤 총구간 수와 최대 피크를 요약합니다. 먼저 보고서를 만들고, 그 보고서의 요약 한 줄로 답을 구합니다.

**질문 1의 뜻 · 점검 실행**　Fieldnote 폴더에서 `python3 capture_report.py`를 한 번 실행하고 완료 여부를 한 문장으로 알려 달라는 요청입니다. 이 단계에서 다음 질문의 근거가 될 실행 결과가 생깁니다.

```text
Use run_command to execute exactly `python3 capture_report.py` once in this project. When the command finishes, confirm in one sentence. Answer in Korean if possible.
```

1. **명령을 확인하고 허용합니다.** **이 작업을 실행할까요?** 카드에 `python3 capture_report.py`가 보이면 **허용**을 누릅니다. 실행 뒤 **이 답변의 작업**을 펼쳐 **명령 실행 · 완료**를 확인합니다. 검증 때 명령의 출력은 **10,378 bytes**였습니다.
2. **방금 생성한 로그를 고릅니다.** **자료 · 컨텍스트 → Source · Runtime Pointer → Runtime**에서 **현재 세션의 Runtime Pointer** 목록의 최신 실행 항목 옆 동그라미를 선택합니다. 비어 있으면 **Runtime 목록 새로고침**을 누릅니다. 검증 때 목록에 표시된 저장 항목의 크기는 **10,405 bytes**였습니다.
3. **합계가 적힌 위치를 찾습니다.** 개별 `METER` 줄에는 한 구간의 값만 있습니다. **Source · Runtime 부분 읽기와 검색 → 포인터 내용 검색**에 보고서의 요약 표식 `CAPTURE_SUMMARY`를 입력하고 **포인터 검색**을 누릅니다. 기본 설정은 **기록 4개 × 기록당 48구간 = 측정 192줄**이므로, 그다음 **193번째 줄**에 요약이 나옵니다. 줄 번호는 검색 결과에서 확인하면 됩니다.
4. **요약 한 줄을 질문에 붙입니다.** 검색한 줄에는 `windows=192`와 `loudest_dbfs=-3`가 함께 있습니다. 같은 패널의 **읽기 범위 → 줄 범위**에서 **시작 줄**과 **끝 범위 (선택)**에 검색 결과의 줄 번호 `193`을 각각 넣고 **범위 읽기**를 누릅니다. 두 칸을 같게 지정하면 측정값 192줄을 다시 읽지 않고 두 답이 담긴 한 줄만 첨부합니다. 패널을 닫고 입력창 위의 **선택 자료**를 확인합니다.

**질문 2의 뜻 · 결과 해석**　선택한 요약 줄만 보고 측정 구간 수와 최대 피크를 알려 달라는 요청입니다. 첫 질문에서 만든 로그를 그대로 사용합니다.

```text
Using only the selected CAPTURE_SUMMARY line, how many windows were measured and what was the loudest peak in dBFS? Answer in Korean if possible.
```

**성공 확인**　답은 **192개 구간, −3 dBFS**입니다. **답변에 사용한 근거**에서 `securecode://runtime/…`와 **원본 byte 10322–10377**을 찾습니다. 이 범위가 방금 선택한 `CAPTURE_SUMMARY windows=192 loudest_dbfs=-3 kit=Reed-04` 한 줄과 일치합니다. 이 답변은 부록 C에서 다시 사용합니다.

## 2. Source Pointer · 장비 설정에서 방풍 커버 이름 읽기

**해결할 질문**　“장비 인계 목록에 방풍 커버 이름을 어떤 영문으로 적어야 할까?” 설정값의 철자가 필요하므로 정답을 담은 설정 항목을 찾고, 파일에서 그 항목이 적힌 한 줄을 근거로 첨부합니다.

1. **설정 원본을 등록합니다.** **자료 · 컨텍스트 → Source · Runtime Pointer**의 **등록할 외부 파일의 호스트 경로**에 아래 경로를 붙여 넣고 **지정한 파일 등록**을 누릅니다. **Source → 등록한 Source**에서 `recorder.json` 옆 동그라미를 선택합니다.

   ```text
   /Users/oscar/Desktop/SecureCode/Fieldnote/reference/recorder.json
   ```

2. **방풍재 항목의 값만 확인합니다.** **Source · Runtime 부분 읽기와 검색 → 읽기 범위 → JSON 경로**를 선택합니다. **JSON Pointer 경로**에 `/profile/wind_guard`를 입력하고 **범위 읽기**를 누릅니다. 이 경로는 `profile` 설정 안의 방풍재 항목을 가리키며, 결과는 **"double fleece"**입니다.
3. **값을 원본 위치와 연결합니다.** JSON 경로 조회는 값을 보여 줍니다. 답변에도 파일의 실제 근거를 남기려면 **읽기 범위 → 줄 범위**로 바꾸고 **시작 줄**과 **끝 범위 (선택)**에 각각 `5`를 넣어 **범위 읽기**를 누릅니다. [장비 설정 파일](reference/recorder.json)의 5번째 줄에는 키와 값이 함께 적혀 있습니다. `"wind_guard": "double fleece"`가 보이면 패널을 닫고 **선택 자료**가 붙었는지 확인합니다.

**질문의 뜻 · 원래 철자 확인**　첨부한 장비 설정 줄에서 `wind_guard` 값을 그대로 옮겨 달라는 요청입니다. 설명은 한국어로 하더라도 설정값은 영문으로 유지합니다.

```text
From the selected recorder.json line, what is the exact wind_guard value? Keep the English value and answer in Korean if possible.
```

**성공 확인**　답에 **double fleece**, **답변에 사용한 근거**에 `source securecode://source/…`와 **원본 byte 66–99**가 표시됩니다. 오른쪽 패널의 파일 이름과 revision을 보면 어느 설정 파일을 읽었는지도 확인할 수 있습니다.

## 3. PDF · 현장 수첩 2쪽에서 복귀 신호 찾기

**해결할 질문**　“현장 녹음 중 출발 위치로 돌아왔을 때, 녹음기에 어떤 두 단어를 말해야 할까?” 수첩은 출발 위치에 도착하면 복귀 신호를 한 번 말해 녹음에 그 지점을 남기도록 안내합니다. 신호를 현장팀에 정확히 전달할 수 있도록 두 단어와 근거 쪽수를 찾습니다. 등록할 자료는 2쪽짜리 [현장 수첩](reference/field-guide.pdf)입니다. 시각 실습을 따라가는 데 사용하는 A4 설명서는 별도 문서입니다.

1. **수첩을 등록하고 읽을 자료로 고릅니다.** **자료 · 컨텍스트 → Source · Runtime Pointer → 등록할 외부 파일의 호스트 경로**에 아래 경로를 붙여 넣고 **지정한 파일 등록**을 누릅니다. **Source → 등록한 Source**에서 `field-guide.pdf`의 동그라미를 선택합니다.

   ```text
   /Users/oscar/Desktop/SecureCode/Fieldnote/reference/field-guide.pdf
   ```

2. **쪽별로 검색할 수 있게 텍스트를 추출합니다.** 패널 아래 **PDF parsing job → PDF parse job 시작**을 누릅니다. **ready · 원본 2쪽**은 두 쪽의 처리가 끝났다는 뜻입니다. 신호가 적힌 쪽은 다음 검색에서 찾습니다.
3. **신호를 소개하는 문장으로 위치를 찾습니다.** 위쪽 **Source · Runtime 부분 읽기와 검색 → 포인터 내용 검색**에 `The return cue is`를 입력하고 **포인터 검색**을 누릅니다. 신호 자체를 미리 몰라도 이 표현으로 해당 문장이 **원본 PDF 2쪽 · byte 185–214**에 있음을 찾을 수 있습니다.
4. **문장이 속한 쪽을 첨부합니다.** **읽기 범위 → PDF 페이지**에서 **시작 페이지**와 **끝 범위 (선택)**를 모두 `2`로 지정하고 **범위 읽기**를 누릅니다. 서비스 출처에 **원본 PDF 2쪽 · byte 0–393**, 본문에 **The return cue is AMBER REED.**가 보이면 패널을 닫습니다. 이렇게 고르면 모델이 신호의 철자와 쪽수를 함께 대조할 수 있습니다.

**질문의 뜻 · 신호 원문 확인**　선택한 수첩 페이지에서 복귀 신호를 찾아 두 단어의 철자와 대문자를 인쇄된 그대로 답해 달라는 요청입니다.

```text
On the selected page of field-guide.pdf, what is the return cue? Keep the two English words exactly as printed. Answer in Korean if possible.
```

**성공 확인**　답은 **AMBER REED**입니다. **답변에 사용한 근거**의 **원본 PDF 2쪽**과 수첩 2쪽의 **Return cue**를 대조합니다. 부록 B에서 이 답변의 근거 주소를 다시 사용합니다.

## 4. R0 인덱스 · 레벨 분류 함수를 찾아 답변과 대조하기

**해결할 질문**　“웹 도감의 ‘방파제의 잔물결’은 −6 dBFS인데 왜 레벨 주의가 붙을까?” 이 표시를 결정하는 함수 이름은 `classifyPeak`입니다. 경계값 −6을 포함하는 쪽이 어디인지 원본 비교식에서 확인합니다.

1. **코드 검색을 준비합니다.** 입력창에 앞서 읽은 PDF가 **선택 자료**로 남아 있으면 **×(선택 자료 포함 해제)**를 누릅니다. 왼쪽 아래 **인덱스 생성·갱신**에서 **Fieldnote**만 체크하고 **1개 생성·갱신**을 눌러 프로젝트의 함수 이름과 파일 위치를 검색할 수 있게 합니다. **색인 3 · 실패 0**과 revision 번호를 확인하고 **닫기**를 누릅니다. HTML·CSS·문서가 제외되어 **부분 완료**로 표시될 수 있습니다.
2. **이름으로 찾은 후보의 구현을 읽습니다.** **자료 · 컨텍스트 → R0 원문 · 컨텍스트 예산**에서 **심볼·파일 검색어**에 `classifyPeak`를 넣고 **원문 심볼 검색**을 누릅니다. **classifyPeak · archive.js:2-8** 후보를 선택한 뒤 **선택한 원문 묶음 읽기**를 누릅니다. **Symbol Bundle**의 `peakDb >= -6`와 `return "hot"`를 함께 보면 −6인 경우에도 해당 분기로 들어간다는 것을 확인할 수 있습니다.
3. **모델에 들어갈 근거를 미리 봅니다.** 아래 영어 문장을 먼저 패널의 **예산을 확인할 실제 질문**에 넣고 **컨텍스트 미리보기**를 누릅니다. **호스트 컨텍스트 계획**에서 `archive.js`의 줄 범위와 예산을 확인합니다. 미리보기는 전달될 근거를 확인하는 단계입니다. 실제 답을 받으려면 패널을 닫고 대화 입력창에 같은 문장을 보내세요.

**질문의 뜻 · 경계값 판정**　`archive.js`의 `classifyPeak` 주석에 따르면 정확히 −6 dBFS일 때 어떤 영어 레이블이 적용되는지, 그 값을 인용해 달라는 요청입니다.

```text
According to the comment in classifyPeak in archive.js, which English label applies at exactly -6 dBFS? Answer in Korean if possible and quote the label.
```

**성공 확인**　답은 **"hot"**이고 **답변에 사용한 근거**에는 **archive.js:2-8**이 보입니다. 웹 도감의 **물가 → 방파제의 잔물결**을 열면 이 분류가 **레벨 주의 · -6 dBFS**로 표시됩니다.

## 부록 · 대화에서 개별 도구의 실행 이력 확인하기

앞에서는 사람이 패널에서 근거를 골랐습니다. 이제 같은 대화에서 모델에게 파일 찾기·검색·부분 읽기를 맡깁니다. **답변에 사용한 근거**는 무엇을 읽었는지 보여 주고, **이 답변의 작업**은 그 근거에 도달하려고 어떤 도구를 실행했는지 보여 줍니다. 답변이 끝나면 **이 답변의 작업**을 펼치고 각 줄의 **완료** 표시를 확인하세요. **상세 기록**에서 해당 작업의 요약을 볼 수 있습니다.

B와 C의 `POINTER`는 내 대화에서 생성된 자료의 주소를 넣을 자리입니다. B는 본문 3의 PDF 답변, C는 본문 1의 두 번째 답변에서 **답변에 사용한 근거**를 찾으세요. `securecode://`부터 `?v=1`처럼 버전 숫자가 끝나는 곳까지 복사합니다. 주소 뒤의 공백·가운뎃점·revision 표시는 빼고, 버전 값은 내 화면에 보이는 숫자를 그대로 사용합니다.

### A. 파일 목록 → 검색 → 한 줄 읽기

**해결할 질문**　“내가 설정 줄을 직접 붙여 주지 않아도 모델이 방풍재 이름을 찾아올 수 있을까?” 본문 2에서는 설정 파일과 줄을 직접 골랐습니다. 이번에는 모델이 `reference` 폴더 목록에서 파일을 확인하고, `wind_guard`를 검색해 해당 줄을 읽도록 합니다. 파일 이름을 알아내는 일, 항목을 찾는 일, 원문을 확인하는 일이 작업 이력에 따로 남습니다.

**질문의 뜻 · 파일에서 설정 찾기**　자료 폴더를 확인하고 장비 설정에서 방풍재 항목을 검색한 뒤 5번째 줄만 읽어, 거기에 적힌 이름을 답해 달라는 요청입니다.

```text
Call list_files on reference. Then call search_file for wind_guard in reference/recorder.json and read_file for line 5 only. What wind guard is listed? Answer in Korean if possible.
```

**성공 확인**　**이 답변의 작업**을 펼쳐 **파일 목록 · 완료**, **파일 검색 · 완료**, **파일 부분 읽기 · 완료**를 차례로 확인합니다. 답의 **double fleece**를 본문 2에서 읽은 설정값과 대조합니다.

### B. PDF 파싱 → 상태 확인 → 검색 → 한 쪽 읽기

**해결할 질문**　“모델이 수첩을 처리하고 필요한 쪽을 직접 읽어도 같은 복귀 신호가 나올까?” 본문 3의 답변에 있는 `securecode://source/…` 주소로 아래 `POINTER`를 바꿉니다. 파싱 뒤에는 반환된 작업 번호로 완료 상태를 확인하고, 검색으로 문장의 위치를 찾은 다음 해당 쪽을 읽습니다. 2쪽을 처음부터 요청하므로 이어 읽기 값(`cursor`)은 생략합니다.

**질문의 뜻 · PDF에서 복귀 신호 찾기**　같은 수첩을 파싱하고 상태를 확인한 뒤, 신호를 소개하는 문장을 검색하고 2쪽 원문에서 복귀 신호를 읽어 달라는 요청입니다.

```text
Use pdf_parse for POINTER. Call pdf_status with its returned job_id. Use pdf_search for "The return cue is". Call pdf_read_pages with only pointer, start_page 2 and end_page 2. Omit cursor. What is the return cue? Answer in Korean if possible.
```

**성공 확인**　**이 답변의 작업**에서 **PDF 파싱**, **PDF 상태 확인**, **PDF 검색**, **PDF 페이지 읽기**의 **완료**를 각각 확인합니다. 검증 때 네 도구가 각각 한 번에 완료됐습니다. 재시도가 있다면 마지막 완료 행을 보세요. 답은 **AMBER REED**, **답변에 사용한 근거**는 **원본 PDF 2쪽**입니다. 본문 3에서 직접 읽은 쪽과 같습니다.

### C. 실행 기록 검색 → 요약 한 줄 읽기

**해결할 질문**　“아까 점검을 다시 실행하지 않고 그때의 측정 구간 수를 검산할 수 있을까?” 본문 1의 두 번째 답변에서 `securecode://runtime/…` 주소를 복사해 아래 `POINTER`와 바꿉니다. 이 주소가 같은 대화에 보관된 바로 그 실행 결과를 지정합니다. 먼저 요약 표식이 있는지 검색한 뒤 본문 1에서 찾은 193번째 줄만 다시 읽습니다. 중괄호 안의 시작·끝 줄 번호를 그대로 둡니다.

**질문의 뜻 · 기존 실행 결과 검산**　저장한 로그에서 `CAPTURE_SUMMARY`를 검색하고 193번째 줄을 읽어, 그 안의 측정 구간 수를 알려 달라는 요청입니다.

```text
Call runtime_search on POINTER for CAPTURE_SUMMARY. Then call runtime_read with the same pointer and selector {"type":"line","start":193,"end":193}. Omit cursor. Report the window count in Korean if possible.
```

**성공 확인**　**실행 결과 검색 · 완료**와 **실행 결과 부분 읽기 · 완료**가 보이고 답은 **192개**입니다. **답변에 사용한 근거**의 **원본 byte 10322–10377**을 본문 1의 범위와 대조하면 같은 로그의 같은 줄을 읽었음을 확인할 수 있습니다.

### D. R0 코드 검색 → 검색한 함수의 원문 읽기

**해결할 질문**　“모델도 레벨 분류 함수를 직접 찾아 −6 dBFS의 판정을 설명할 수 있을까?” 본문 4에서 Fieldnote의 인덱스를 만든 뒤 진행합니다. 이번에는 모델이 함수 이름을 검색해 후보 하나를 고릅니다. 원문 읽기에는 검색 결과의 후보 번호와 인덱스 버전을 함께 써야 바로 그 후보의 구현을 읽을 수 있습니다.

**질문의 뜻 · 코드로 경계값 설명**　`classifyPeak` 후보 하나를 찾아 그 후보의 원문을 읽고, −6 dBFS에서 반환하는 레이블을 답해 달라는 요청입니다.

```text
Call code_search with query classifyPeak and limit 1. Call code_read using the exact candidate_id and index_revision returned. Which label does the function return at -6 dBFS? Answer in Korean if possible.
```

**성공 확인**　**이 답변의 작업**에 **R0 코드 검색 · 완료**와 **R0 원문 읽기 · 완료**가 모두 보입니다. 답은 **hot**이며, **답변에 사용한 근거**의 **archive.js:2-8**이 본문 4에서 확인한 함수와 일치합니다.

### E. 파일 쓰기 승인 → 저장한 한 줄 확인하기

**해결할 질문**　“검토를 마쳤다는 확인증을 폴더에 남기고, 디스크에 실제로 쓴 내용까지 확인할 수 있을까?” 대화가 끝난 뒤에도 다른 사람이 검토 완료를 확인할 수 있도록 프로젝트에 짧은 텍스트 파일을 만듭니다. 먼저 Finder에서 Fieldnote 폴더에 `review-slip.txt`가 이미 있는지 확인합니다. 처음 배포된 프로젝트에는 이 파일이 없습니다. 보관 중인 파일이 있으면 아래 질문의 파일명을 새 이름으로 바꾸세요.

**질문의 뜻 · 확인증 작성과 재확인**　`review-slip.txt`에 `FIELDNOTE REVIEWED`만 쓰고, 저장한 파일을 다시 열어 내용이 일치하는지 확인해 달라는 요청입니다.

```text
Use write_file to create review-slip.txt with exactly the text FIELDNOTE REVIEWED. Then use read_file to verify the saved text. Answer in Korean if possible.
```

1. **저장할 내용을 검토합니다.** **이 파일 변경을 허용할까요?** 카드에서 대상이 **write review-slip.txt**이고 문구가 **FIELDNOTE REVIEWED**인지 확인합니다. 새 이름을 지정했다면 카드에도 그 이름이 보여야 합니다. 일치하면 **허용**, 보관 중인 파일을 덮어쓰게 된다면 **거절**을 누릅니다.
2. **실제로 저장됐는지 확인합니다.** **이 답변의 작업**에서 **파일 쓰기 · 완료** 뒤에 **파일 부분 읽기 · 완료**가 있는지 봅니다. 두 번째 작업이 방금 쓴 파일을 실제로 열어 확인한 기록입니다.

**성공 확인**　답에 **FIELDNOTE REVIEWED**, **답변에 사용한 근거**에 **원본 byte 0–18**이 나타납니다. Finder에서 생성된 파일을 열어 문구를 대조할 수 있습니다.

## 시연 검증 기록

2026년 11월 15일 이 Mac의 Local Desk에서 **Qwen 2.5 · 7B**를 선택하고 본문과 부록의 질문을 전송했습니다. 시각 실습서 PDF를 추가하기 전 색인 결과는 **발견 10 · 색인 3 · 제외 7 · 실패 0**이었습니다. 문서 수에 따라 발견·제외 수는 달라집니다. 본문 네 단계의 답변에서 각각 실행 로그의 193번째 줄, 설정 파일의 5번째 줄, PDF 2쪽, `archive.js`의 2–8번째 줄을 근거와 대조했습니다. 부록까지 포함해 서로 다른 도구 13개의 **완료** 행을 확인했습니다. 같은 질문도 답변의 문장이나 작업 횟수는 달라질 수 있으니, 시연에서는 각 단계에 적힌 값과 출처를 확인하세요.
