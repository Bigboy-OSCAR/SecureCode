(function () {
  const pointerConfigs = {
    source: {
      title: "source://는 manifest를 통해 disk 파일을 찾아가고, extractor가 필요한 부분만 읽는다",
      cards: [
        {
          badge: "1",
          title: "원본 데이터",
          body: "파일은 LLM context 밖 disk에 그대로 둔다.",
          code: ["sources/json/tenant_snapshot.json", "sources/docs/ops_runbook.md"]
        },
        {
          badge: "2",
          title: "Source catalog",
          body: "LLM은 원본 대신 pointer와 hint만 본다.",
          code: ["source://json/tenant_snapshot", "kind: json", "tool: extract_json_field"]
        },
        {
          badge: "3",
          title: "LLM tool 선택",
          body: "질문을 보고 어떤 extractor를 부를지 JSON으로 고른다.",
          code: ["tool: extract_json_field", "path: tenants.northwind-prod"]
        },
        {
          badge: "4",
          title: "Resolver 접근",
          body: "source:// 주소를 manifest에서 실제 file path로 바꾼다.",
          code: ["pointer -> manifest lookup", "file path -> open/read"]
        },
        {
          badge: "5",
          title: "형식별 가공",
          body: "log는 grep, doc은 section, JSON은 path로 일부만 추출한다.",
          code: ["grep around request_id", "extract section", "extract JSON path"]
        },
        {
          badge: "6",
          title: "LLM 전달",
          body: "최종 prompt에는 작은 근거와 질문만 들어간다.",
          code: ["runtime_pointer_enabled: true", "max_context_policy: pointer-first"]
        }
      ],
      packetLabels: ["source://", "tool call", "snippet"]
    },
    runtime: {
      title: "runtime://는 파일 경로가 아니라 실행 중 저장된 object id를 RuntimeStore에서 찾는다",
      cards: [
        {
          badge: "1",
          title: "Producer 실행",
          body: "tool이 log, markdown, dict 같은 큰 중간 결과를 만든다.",
          code: ["fetch_tenant_snapshot()", "collect_checkout_trace()"]
        },
        {
          badge: "2",
          title: "RuntimeStore 저장",
          body: "raw output은 process-local memory에 보관한다.",
          code: ["put(raw_value) -> id 0001", "kind: json / log / doc"]
        },
        {
          badge: "3",
          title: "Runtime pointer",
          body: "LLM에는 raw output 대신 짧은 주소와 tool 목록만 보인다.",
          code: ["runtime://json/.../0001", "tool: extract_runtime_json_path"]
        },
        {
          badge: "4",
          title: "Mirrored tool",
          body: "tool wrapper가 pointer를 받으면 store에서 raw value를 resolve한다.",
          code: ["resolve(pointer)", "raw = store[pointer]"]
        },
        {
          badge: "5",
          title: "필요 부분 추출",
          body: "원래 tool이 기대하는 값으로 바꾼 뒤 field나 section만 뽑는다.",
          code: ["extract_runtime_json_path()", "grep_runtime_log()"]
        },
        {
          badge: "6",
          title: "LLM 전달",
          body: "큰 tool output이 아니라 추출 결과만 final answer prompt에 들어간다.",
          code: ["reason: fraud_guard", "retry_after_ms: 750"]
        }
      ],
      packetLabels: ["runtime://", "resolve", "extracted"]
    }
  };

  const symbolCards = [
    {
      badge: "1",
      title: "원본 코드",
      body: "parser는 파일을 읽고 함수, class, method의 위치를 찾는다.",
      code: ["def validate_token(token):", "    if expired:", "        raise ValueError(MSG)"]
    },
    {
      badge: "2",
      title: "AST parser",
      body: "문자열 검색이 아니라 Python AST로 구조를 읽는다.",
      code: ["FunctionDef: validate_token", "ClassDef: InvoiceCalculator", "Assign: TOKEN_EXPIRED_MESSAGE"]
    },
    {
      badge: "3",
      title: "symbol_index 형식",
      body: "각 symbol은 파일, 이름, 줄 범위, URI를 가진 record가 된다.",
      code: ["path: services/auth.py", "kind: function", "uri: memory://...::validate_token"]
    },
    {
      badge: "4",
      title: "LLM 판단",
      body: "질문 키워드와 compact outline을 비교해 필요한 URI를 고른다.",
      code: ["question: expired token literal?", "selected: ...::validate_token"]
    },
    {
      badge: "5",
      title: "resolver / bundle",
      body: "선택된 symbol의 줄 범위를 읽고, 참조 상수와 helper까지 확장한다.",
      code: ["read_symbol(uri)", "+ TOKEN_EXPIRED_MESSAGE", "+ same-file helper"]
    },
    {
      badge: "6",
      title: "LLM 전달",
      body: "LLM은 전체 repo가 아니라 근거 symbol bundle로 답한다.",
      code: ["validate_token body", "TOKEN_EXPIRED_MESSAGE = 'TOKEN_EXPIRED'"]
    }
  ];

  function makeCode(lines) {
    return `<pre>${lines.map((line) => escapeHtml(line)).join("\n")}</pre>`;
  }

  function escapeHtml(value) {
    return value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderProcessCards(cards) {
    return cards
      .map((card, index) => {
        return `
          <article class="process-card process-card-${index + 1}">
            <span class="process-badge">${card.badge}</span>
            <h4>${card.title}</h4>
            <p>${card.body}</p>
            ${makeCode(card.code)}
          </article>
        `;
      })
      .join("");
  }

  function renderPointerVisualizer(root, config, type) {
    root.innerHTML = `
      <div class="viz-stage detail-stage ${type}-detail">
        <div class="viz-title-row">
          <strong>${config.title}</strong>
          <button class="viz-button" type="button">다시 재생</button>
        </div>
        <div class="detail-canvas">
          <div class="process-grid">${renderProcessCards(config.cards)}</div>
          <div class="process-rail" aria-hidden="true">
            <span>${config.packetLabels[0]}</span>
            <span>${config.packetLabels[1]}</span>
            <span>${config.packetLabels[2]}</span>
            <i class="rail-packet"></i>
          </div>
        </div>
      </div>
    `;
  }

  function renderSymbolVisualizer(root) {
    root.innerHTML = `
      <div class="viz-stage detail-stage symbol-detail">
        <div class="viz-title-row">
          <strong>원본 코드에서 symbol_index를 만들고, LLM은 URI를 선택한 뒤 bundle을 읽는다</strong>
          <button class="viz-button" type="button">다시 재생</button>
        </div>
        <div class="detail-canvas">
          <div class="process-grid">${renderProcessCards(symbolCards)}</div>
          <div class="process-rail symbol-rail" aria-hidden="true">
            <span>AST scan</span>
            <span>index JSON</span>
            <span>memory:// URI</span>
            <span>bundle</span>
            <i class="rail-packet"></i>
          </div>
        </div>
      </div>
    `;
  }

  function renderSelfExtend(root) {
    const tokens = Array.from({ length: 18 }, (_, index) => {
      const isOverflow = index > 10;
      const isPasskey = index === 13;
      const label = index === 10 ? "4k" : isPasskey ? "key" : "";
      return `<i class="context-token ${isOverflow ? "overflow-token" : ""} ${isPasskey ? "passkey-token" : ""}">${label}</i>`;
    }).join("");

    root.innerHTML = `
      <div class="viz-stage detail-stage self-detail">
        <div class="viz-title-row">
          <strong>Self-Extend는 위치 정보를 group 단위로 접어 context 수용량을 늘린다</strong>
          <button class="viz-button" type="button">다시 재생</button>
        </div>
        <div class="self-grid">
          <section class="self-panel base-window">
            <h4>1. 기본 context window</h4>
            <p>4k 이후 token은 기본 실행에서 overflow가 된다.</p>
            <div class="context-strip">${tokens}</div>
            <div class="limit-line"><span>기본 한계</span></div>
          </section>
          <section class="self-panel grouped-window">
            <h4>2. Group attention</h4>
            <p>먼 token 여러 개를 하나의 group 좌표로 묶어 더 긴 입력을 같은 창 안에 넣는다.</p>
            <div class="group-row">
              <span>real pos 4096-8192</span>
              <i></i>
              <span>group pos 2048-4096</span>
            </div>
            <div class="group-row">
              <span>G=2</span>
              <i></i>
              <span>약 2배 수용</span>
            </div>
            <div class="group-row">
              <span>G=4</span>
              <i></i>
              <span>약 4배 수용</span>
            </div>
            <div class="scan-lens"></div>
          </section>
          <section class="self-panel attention-window">
            <h4>3. 정확도 trade-off</h4>
            <p>가까운 token은 자세히 보고, 먼 token은 압축된 주소로 본다. 그래서 입력은 들어가도 정확한 회수는 실패할 수 있다.</p>
            <div class="attention-map">
              <span class="near">local exact</span>
              <span class="far">grouped distant</span>
              <b class="attention-dot"></b>
            </div>
          </section>
        </div>
      </div>
    `;
  }

  function bindReplay(root) {
    const button = root.querySelector(".viz-button");
    if (!button) return;
    button.addEventListener("click", () => {
      root.classList.add("is-restarting");
      window.setTimeout(() => root.classList.remove("is-restarting"), 80);
    });
  }

  function renderVisualizers() {
    document.querySelectorAll("[data-visualizer]").forEach((root) => {
      const type = root.getAttribute("data-visualizer");
      if (type === "source" || type === "runtime") {
        renderPointerVisualizer(root, pointerConfigs[type], type);
      }
      if (type === "symbol") {
        renderSymbolVisualizer(root);
      }
      if (type === "selfextend") {
        renderSelfExtend(root);
      }
      bindReplay(root);
    });
  }

  window.addEventListener("DOMContentLoaded", renderVisualizers);
})();
