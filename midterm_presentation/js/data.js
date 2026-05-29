window.DeckData = {
  visualizers: {
    pointer: "./pointer_data_visualizer.html",
    selfExtend: "./self_extend_visualizer.html",
    symbol: "./symbol_index_filtered_bundle_visualizer.html"
  },
  charts: {
    rawTokenPressure: {
      unit: " tokens",
      scale: "log",
      sort: "desc",
      note: "Log scale. Lower is easier to fit in context.",
      rows: [
        { label: "runtime full", value: 131136, color: "#c94d4d" },
        { label: "source full", value: 120208, color: "#c94d4d" },
        { label: "symbol full repo", value: 67188, color: "#c94d4d" },
        { label: "self code context", value: 4854, color: "#d99022" }
      ]
    },
    sourceAccuracy: {
      unit: "%",
      sort: "desc",
      note: "Medium scale. Higher is better.",
      rows: [
        { label: "pointer_oracle", value: 100, color: "#16857a" },
        { label: "pointer_select", value: 100, color: "#1f6feb" },
        { label: "full_source", value: 33.3, color: "#c94d4d" }
      ]
    },
    sourceTokens: {
      unit: " tokens",
      scale: "log",
      sort: "desc",
      note: "Medium scale. Log scale.",
      rows: [
        { label: "full_source", value: 120208, color: "#c94d4d" },
        { label: "pointer_select", value: 780, color: "#1f6feb" },
        { label: "pointer_oracle", value: 286, color: "#16857a" }
      ]
    },
    sourceWall: {
      unit: " s",
      sort: "desc",
      note: "Medium scale. Lower is faster.",
      rows: [
        { label: "full_source", value: 22.117, color: "#c94d4d" },
        { label: "pointer_select", value: 6.423, color: "#1f6feb" },
        { label: "pointer_oracle", value: 2.443, color: "#16857a" }
      ]
    },
    runtimeAccuracy: {
      unit: "%",
      sort: "desc",
      note: "Medium scale. Higher is better.",
      rows: [
        { label: "pointer_oracle", value: 100, color: "#16857a" },
        { label: "pointer_select", value: 100, color: "#1f6feb" },
        { label: "full_runtime", value: 33.3, color: "#c94d4d" }
      ]
    },
    runtimeTokens: {
      unit: " tokens",
      scale: "log",
      sort: "desc",
      note: "Medium scale. Log scale.",
      rows: [
        { label: "full_runtime", value: 131136, color: "#c94d4d" },
        { label: "pointer_select", value: 757, color: "#1f6feb" },
        { label: "pointer_oracle", value: 311, color: "#16857a" }
      ]
    },
    runtimeWall: {
      unit: " s",
      sort: "desc",
      note: "Medium scale. Lower is faster.",
      rows: [
        { label: "full_runtime", value: 26.27, color: "#c94d4d" },
        { label: "pointer_select", value: 6.891, color: "#1f6feb" },
        { label: "pointer_oracle", value: 2.61, color: "#16857a" }
      ]
    },
    symbolEasyWall: {
      unit: " s",
      scale: "log",
      sort: "desc",
      note: "Medium easy tasks. Log scale.",
      rows: [
        { label: "full_repo", value: 612.869, color: "#c94d4d" },
        { label: "symbol_select", value: 181.191, color: "#1f6feb" },
        { label: "full_file", value: 2.286, color: "#d99022" },
        { label: "symbol_oracle", value: 2.131, color: "#16857a" },
        { label: "line_span", value: 2.12, color: "#2f8a4c" }
      ]
    },
    symbolEasyTokens: {
      unit: " tokens",
      scale: "log",
      sort: "desc",
      note: "Medium easy tasks. Log scale.",
      rows: [
        { label: "full_repo", value: 67188, color: "#c94d4d" },
        { label: "symbol_select", value: 33871, color: "#1f6feb" },
        { label: "full_file", value: 256, color: "#d99022" },
        { label: "symbol_oracle", value: 199, color: "#16857a" },
        { label: "line_span", value: 199, color: "#2f8a4c" }
      ]
    },
    symbolHardAccuracy: {
      unit: "%",
      sort: "desc",
      note: "Hard tasks require surrounding context.",
      rows: [
        { label: "full_file", value: 33.3, color: "#d99022" },
        { label: "bundle_oracle", value: 33.3, color: "#16857a" },
        { label: "filtered_bundle", value: 33.3, color: "#7157c8" },
        { label: "symbol_oracle", value: 0, color: "#c94d4d" },
        { label: "symbol_select", value: 0, color: "#c94d4d" }
      ]
    },
    symbolSelectorCost: {
      unit: " tokens",
      scale: "log",
      sort: "desc",
      note: "Hard tasks. Filtered bundle cuts selector context.",
      rows: [
        { label: "old selector", value: 33922, color: "#c94d4d" },
        { label: "filtered bundle", value: 587, color: "#7157c8" }
      ]
    },
    selfPasskey: {
      unit: "%",
      sort: "desc",
      note: "Llama-2 passkey retrieval. Higher is better.",
      rows: [
        { label: "off", value: 66.7, color: "#d99022" },
        { label: "G=2", value: 0, color: "#c94d4d" },
        { label: "G=4", value: 0, color: "#c94d4d" }
      ]
    },
    selfCapacity: {
      unit: " ctx",
      sort: "desc",
      note: "Reported llama.cpp context size.",
      rows: [
        { label: "G=4", value: 16608, color: "#7157c8" },
        { label: "G=2", value: 8416, color: "#1f6feb" },
        { label: "off", value: 4320, color: "#d99022" }
      ]
    },
    selfCodeAssist: {
      unit: "%",
      sort: "desc",
      note: "Code assistance benchmark. Higher is better.",
      rows: [
        { label: "off", value: 0, color: "#c94d4d" },
        { label: "G=2", value: 0, color: "#c94d4d" },
        { label: "G=4", value: 0, color: "#c94d4d" }
      ]
    },
    selfPpl: {
      unit: " PPL",
      scale: "log",
      sort: "desc",
      note: "PG-19 baseline only. Lower is better.",
      rows: [
        { label: "Q5 ctx4096", value: 309.3053, color: "#c94d4d" },
        { label: "Q4 ctx4096", value: 304.6347, color: "#c94d4d" },
        { label: "Q5 ctx2048", value: 7.8592, color: "#16857a" },
        { label: "Q4 ctx2048", value: 7.8529, color: "#16857a" }
      ]
    },
    overallPrompt: {
      unit: " tokens",
      scale: "log",
      sort: "desc",
      note: "Representative medium prompt sizes. Log scale.",
      rows: [
        { label: "runtime full", value: 131136, color: "#c94d4d" },
        { label: "source full", value: 120208, color: "#c94d4d" },
        { label: "symbol full repo", value: 67188, color: "#c94d4d" },
        { label: "source select", value: 780, color: "#1f6feb" },
        { label: "runtime select", value: 757, color: "#1f6feb" },
        { label: "filtered bundle", value: 587, color: "#7157c8" }
      ]
    }
  },
  slides: [
    {
      title: "Overview",
      className: "cover-slide",
      html: `
        <div class="cover-layout">
          <div>
            <p class="eyebrow">runtime pointer / self-extend / source pointer / symbol index</p>
            <h1>Experiment Results for Local LLM Context Access</h1>
            <p class="lead">A concise comparison of four ways to keep local code assistance useful when raw code, logs, documents, JSON, and tool output exceed the practical prompt budget.</p>
            <div class="cover-meta">
              <span class="meta-pill">Qwen2.5 Coder 7B Q5_K_M</span>
              <span class="meta-pill">Llama-2-7B-chat Q4/Q5</span>
              <span class="meta-pill">llama.cpp on M3 Pro</span>
            </div>
          </div>
          <div class="architecture-board">
            <div class="arch-row single">
              <div class="arch-cell">User request<small>question, log, failing test, code task</small></div>
            </div>
            <div class="arch-row">
              <div class="arch-cell arch-symbol">Symbol index<small>code symbols</small></div>
              <div class="arch-cell arch-self">Self-Extend<small>long prompt fallback</small></div>
              <div class="arch-cell arch-runtime">Runtime pointer<small>tool outputs</small></div>
              <div class="arch-cell arch-source">Source pointer<small>external files</small></div>
            </div>
            <div class="arch-row single">
              <div class="arch-cell">Small evidence context<small>only the selected code, field, section, or log lines</small></div>
            </div>
          </div>
        </div>`
    },
    {
      title: "Target Result",
      html: `
        <div class="split-layout">
          <div>
            <p class="eyebrow">final product</p>
            <h2>The target is a pointer-first local code assistant</h2>
            <p class="lead">Large data stays outside the prompt. The LLM receives compact addresses, chooses tools, and gets only the evidence needed for reasoning or code edits.</p>
            <div class="callout">
              <strong>Design target</strong>
              <p>Use context as a workbench, not as storage. Store raw objects elsewhere and move only the relevant slice into the model prompt.</p>
            </div>
          </div>
          <div>
            <div class="metric-row">
              <div class="metric"><strong>4</strong><span>access strategies tested</span></div>
              <div class="metric"><strong>3</strong><span>visualizers already implemented</span></div>
              <div class="metric"><strong>32k</strong><span>main Qwen context setting</span></div>
            </div>
            <div class="diagram-panel" style="margin-top: 14px;">
              <div class="arch-row single">
                <div class="arch-cell">request -> candidate retrieval -> resolver / extractor -> compact evidence -> LLM answer or patch</div>
              </div>
            </div>
          </div>
        </div>`
    },
    {
      title: "Local LLM Limits",
      html: `
        <div class="slide-heading">
          <p class="eyebrow">problem</p>
          <h2>Why raw context injection fails</h2>
        </div>
        <div class="problem-band">
          <div class="limitation-list">
            <article class="limitation-item"><h3>Context overflow</h3><p>Large logs and JSON exceeded the active 32k context even at small scale.</p></article>
            <article class="limitation-item"><h3>Prompt evaluation cost</h3><p>Medium symbol full repo needed 67,188 tokens and about 613 seconds for one case.</p></article>
            <article class="limitation-item"><h3>Distractor errors</h3><p>Even when raw data fits, irrelevant nearby values can pull the model to the wrong answer.</p></article>
            <article class="limitation-item"><h3>Long-context retrieval is separate</h3><p>Accepting a longer prompt does not guarantee the model can recover the needed fact.</p></article>
          </div>
          <div class="chart-card large"><div class="chart-title">Raw Prompt Token Pressure</div><div data-chart="rawTokenPressure"></div></div>
        </div>`
    },
    {
      title: "Solution Overview",
      html: `
        <div class="slide-heading">
          <p class="eyebrow">four solutions</p>
          <h2>Four approaches and their visualizers</h2>
        </div>
        <div class="card-grid">
          <article class="solution-card"><h3>symbol_index</h3><p>Build stable symbol addresses from source code, then read selected functions, classes, constants, and helpers.</p><div class="tag-list"><span class="tag">memory://symbol</span><span class="tag">bundle</span></div></article>
          <article class="solution-card"><h3>self_extend</h3><p>Use group attention to accept longer prompts when retrieval narrowing is not enough.</p><div class="tag-list"><span class="tag">G=2</span><span class="tag">G=4</span></div></article>
          <article class="solution-card"><h3>runtime_pointer</h3><p>Store large tool outputs in RuntimeStore and pass only runtime addresses between tool calls.</p><div class="tag-list"><span class="tag">runtime://</span><span class="tag">mirrored tools</span></div></article>
          <article class="solution-card"><h3>source_pointer</h3><p>Keep disk files outside the prompt and extract log lines, document sections, or JSON paths by pointer.</p><div class="tag-list"><span class="tag">source://</span><span class="tag">typed extractors</span></div></article>
        </div>
        <div class="visualizer-links" style="margin-top: 18px;">
          <article class="visualizer-link-card"><h3>Pointer Data Visualizer</h3><p>Covers both source_pointer and runtime_pointer tracks.</p><a class="primary-link" href="./pointer_data_visualizer.html" target="_blank" rel="noreferrer">Open visualizer</a></article>
          <article class="visualizer-link-card"><h3>Self-Extend Visualizer</h3><p>Shows overflow, grouped positions, and retrieval verification risk.</p><a class="primary-link" href="./self_extend_visualizer.html" target="_blank" rel="noreferrer">Open visualizer</a></article>
          <article class="visualizer-link-card"><h3>Symbol Bundle Visualizer</h3><p>Shows parser indexing, filtered selection, URI resolution, and bundle context.</p><a class="primary-link" href="./symbol_index_filtered_bundle_visualizer.html" target="_blank" rel="noreferrer">Open visualizer</a></article>
        </div>`
    },
    {
      title: "symbol_index",
      html: `
        <div class="method-layout">
          <div>
            <p class="eyebrow">solution 1</p>
            <h2>symbol_index</h2>
            <p class="lead">Parse the repository into compact symbol records. Resolve selected URIs into code bodies or dependency bundles only when needed.</p>
            <div class="tag-list"><span class="tag">AST parser</span><span class="tag">memory://symbol/file.py::qualname</span><span class="tag">filtered bundle</span></div>
            <p style="margin-top: 20px;"><a class="primary-link" href="./symbol_index_filtered_bundle_visualizer.html" target="_blank" rel="noreferrer">Open symbol visualizer</a></p>
          </div>
          <div class="mini-visual" data-mini-visual="symbol"></div>
        </div>`
    },
    {
      title: "self_extend",
      html: `
        <div class="method-layout">
          <div>
            <p class="eyebrow">solution 2</p>
            <h2>self_extend</h2>
            <p class="lead">Group attention changes inference-time position mapping so prompts beyond the normal window can be accepted.</p>
            <div class="callout">
              <strong>Important distinction</strong>
              <p>It can avoid overflow, but this experiment shows that retrieval quality must still be verified before using it for code edits.</p>
            </div>
            <p style="margin-top: 20px;"><a class="primary-link" href="./self_extend_visualizer.html" target="_blank" rel="noreferrer">Open Self-Extend visualizer</a></p>
          </div>
          <div class="mini-visual" data-mini-visual="self"></div>
        </div>`
    },
    {
      title: "runtime_pointer",
      html: `
        <div class="method-layout">
          <div>
            <p class="eyebrow">solution 3</p>
            <h2>runtime_pointer</h2>
            <p class="lead">A producer tool stores large intermediate values in RuntimeStore. Later tools receive a <code>runtime://</code> address and resolve only the needed part.</p>
            <div class="tag-list"><span class="tag">producer output</span><span class="tag">RuntimeStore</span><span class="tag">mirrored extraction</span></div>
            <p style="margin-top: 20px;"><a class="primary-link" href="./pointer_data_visualizer.html" target="_blank" rel="noreferrer">Open pointer visualizer</a></p>
          </div>
          <div class="mini-visual" data-mini-visual="runtime"></div>
        </div>`
    },
    {
      title: "source_pointer",
      html: `
        <div class="method-layout">
          <div>
            <p class="eyebrow">solution 4</p>
            <h2>source_pointer</h2>
            <p class="lead">Disk files stay in a safe source root. The LLM sees a catalog entry and invokes format-specific tools for logs, markdown, or JSON.</p>
            <div class="tag-list"><span class="tag">grep_log</span><span class="tag">extract_doc_section</span><span class="tag">extract_json_field</span></div>
            <p style="margin-top: 20px;"><a class="primary-link" href="./pointer_data_visualizer.html" target="_blank" rel="noreferrer">Open pointer visualizer</a></p>
          </div>
          <div class="mini-visual" data-mini-visual="source"></div>
        </div>`
    },
    {
      title: "Symbol Results",
      html: `
        <div class="slide-heading compact">
          <p class="eyebrow">experiment results 1</p>
          <h2>symbol_index results</h2>
          <p>Easy tasks show the cost benefit of symbol access. Hard tasks show why single-symbol reads must expand into bundles.</p>
        </div>
        <div class="result-layout">
          <aside class="mode-guide">
            <h3>Compared modes</h3>
            <dl>
              <div><dt>full_repo</dt><dd>Insert the whole repository into the prompt.</dd></div>
              <div><dt>full_file</dt><dd>Assume the target file is already known.</dd></div>
              <div><dt>line_span</dt><dd>Read the exact target line range.</dd></div>
              <div><dt>symbol_oracle</dt><dd>Read the known target symbol only.</dd></div>
              <div><dt>symbol_select</dt><dd>Let the LLM choose from the full symbol index.</dd></div>
              <div><dt>filtered_select_bundle</dt><dd>Filter candidates first, then expand constants and helpers.</dd></div>
            </dl>
          </aside>
          <div class="chart-grid two">
            <div class="chart-card"><div class="chart-title">Easy Task Wall Time</div><div data-chart="symbolEasyWall"></div></div>
            <div class="chart-card"><div class="chart-title">Easy Task Prompt Tokens</div><div data-chart="symbolEasyTokens"></div></div>
            <div class="chart-card"><div class="chart-title">Hard Task Accuracy</div><div data-chart="symbolHardAccuracy"></div></div>
            <div class="chart-card"><div class="chart-title">Selector Cost Improvement</div><div data-chart="symbolSelectorCost"></div></div>
          </div>
        </div>`
    },
    {
      title: "Self-Extend Results",
      html: `
        <div class="slide-heading compact">
          <p class="eyebrow">experiment results 2</p>
          <h2>self_extend results</h2>
          <p>Self-Extend increased accepted context length, but did not recover passkey retrieval or code-assistance accuracy in this environment.</p>
        </div>
        <div class="result-layout">
          <aside class="mode-guide">
            <h3>Compared modes</h3>
            <dl>
              <div><dt>off</dt><dd>Default 4k attention without group attention.</dd></div>
              <div><dt>G=2</dt><dd>Group attention with about 2x reported context.</dd></div>
              <div><dt>G=4</dt><dd>Group attention with about 4x reported context.</dd></div>
              <div><dt>passkey</dt><dd>Recover a hidden 5-digit key from long junk text.</dd></div>
              <div><dt>code assistance</dt><dd>Recover function value, symbol reference, and test failure cause from long repo context.</dd></div>
              <div><dt>PG-19 PPL</dt><dd>Baseline PPL only; group-attention flags were not available.</dd></div>
            </dl>
          </aside>
          <div class="chart-grid two">
            <div class="chart-card"><div class="chart-title">Passkey Success Rate</div><div data-chart="selfPasskey"></div></div>
            <div class="chart-card"><div class="chart-title">Reported Context Capacity</div><div data-chart="selfCapacity"></div></div>
            <div class="chart-card"><div class="chart-title">Code Assistance Success</div><div data-chart="selfCodeAssist"></div></div>
            <div class="chart-card"><div class="chart-title">PG-19 PPL Baseline</div><div data-chart="selfPpl"></div></div>
          </div>
        </div>`
    },
    {
      title: "Runtime Pointer Results",
      html: `
        <div class="slide-heading compact">
          <p class="eyebrow">experiment results 3</p>
          <h2>runtime_pointer results</h2>
          <p>Runtime pointer modes were accurate while keeping prompt size nearly constant as generated runtime objects grew.</p>
        </div>
        <div class="result-layout">
          <aside class="mode-guide">
            <h3>Compared modes</h3>
            <dl>
              <div><dt>full_runtime</dt><dd>Insert the entire producer output into the prompt.</dd></div>
              <div><dt>runtime_pointer_oracle</dt><dd>Use the known correct extraction call.</dd></div>
              <div><dt>runtime_pointer_select</dt><dd>Let the LLM select a tool call from runtime catalog and tool specs.</dd></div>
            </dl>
            <p class="guide-note">Medium: 3/3 success for pointer modes, 1/3 for full runtime. Prompt tokens fell from 131,136 to 757 for selected mode.</p>
          </aside>
          <div class="chart-grid one">
            <div class="chart-card"><div class="chart-title">Medium Accuracy</div><div data-chart="runtimeAccuracy"></div></div>
            <div class="chart-card"><div class="chart-title">Medium Prompt Tokens</div><div data-chart="runtimeTokens"></div></div>
            <div class="chart-card"><div class="chart-title">Medium Wall Time</div><div data-chart="runtimeWall"></div></div>
          </div>
        </div>`
    },
    {
      title: "Source Pointer Results",
      html: `
        <div class="slide-heading compact">
          <p class="eyebrow">experiment results 4</p>
          <h2>source_pointer results</h2>
          <p>Source pointer modes avoided context overflow and removed large disk files from the LLM prompt.</p>
        </div>
        <div class="result-layout">
          <aside class="mode-guide">
            <h3>Compared modes</h3>
            <dl>
              <div><dt>full_source</dt><dd>Insert the whole log, markdown document, or JSON file into the prompt.</dd></div>
              <div><dt>pointer_oracle</dt><dd>Use the known correct extraction call.</dd></div>
              <div><dt>pointer_select</dt><dd>Let the LLM choose an extraction tool from a compact source catalog.</dd></div>
            </dl>
            <p class="guide-note">Medium: 3/3 success for pointer modes, 1/3 for full source. Prompt tokens fell from 120,208 to 780 for selected mode.</p>
          </aside>
          <div class="chart-grid one">
            <div class="chart-card"><div class="chart-title">Medium Accuracy</div><div data-chart="sourceAccuracy"></div></div>
            <div class="chart-card"><div class="chart-title">Medium Prompt Tokens</div><div data-chart="sourceTokens"></div></div>
            <div class="chart-card"><div class="chart-title">Medium Wall Time</div><div data-chart="sourceWall"></div></div>
          </div>
        </div>`
    },
    {
      title: "Overall Conclusion",
      html: `
        <div class="slide-heading compact">
          <p class="eyebrow">synthesis</p>
          <h2>Final comparison and application plan</h2>
        </div>
        <div class="split-layout">
          <div>
            <div class="matrix">
              <div class="matrix-row header"><span>Approach</span><span>Best target</span><span>Experiment result</span><span>Use</span></div>
              <div class="matrix-row"><span>symbol_index</span><span>repository code</span><span>Fast when bundled; old full-index selector was too expensive.</span><strong>default</strong></div>
              <div class="matrix-row"><span>source_pointer</span><span>disk logs, docs, JSON</span><span>3/3 success with stable prompt size.</span><strong>default</strong></div>
              <div class="matrix-row"><span>runtime_pointer</span><span>tool output and intermediate values</span><span>3/3 success with runtime size decoupled from prompt size.</span><strong>default</strong></div>
              <div class="matrix-row"><span>self_extend</span><span>wide background context</span><span>Accepted longer input, but retrieval failed.</span><strong class="fallback">fallback</strong></div>
            </div>
          </div>
          <div class="chart-card large"><div class="chart-title">Representative Medium Prompt Sizes</div><div data-chart="overallPrompt"></div></div>
        </div>`
    },
    {
      title: "Next Steps",
      html: `
        <div class="final-layout">
          <div>
            <p class="eyebrow">conclusion</p>
            <h2>Use retrieval first, length extension last</h2>
            <div class="final-points">
              <article class="final-point"><span>1</span><p>Default external evidence access to <code>source://</code> plus typed extraction tools.</p></article>
              <article class="final-point"><span>2</span><p>Default tool-output reuse to <code>runtime://</code> plus RuntimeStore-backed mirrored tools.</p></article>
              <article class="final-point"><span>3</span><p>Default code access to filtered symbol bundles, not full repository prompts.</p></article>
              <article class="final-point"><span>4</span><p>Keep Self-Extend as an experimental fallback gated by retrieval sanity checks.</p></article>
            </div>
          </div>
          <div class="next-steps">
            <article class="mode-card"><h3>Immediate integration</h3><p>Combine source pointer evidence, runtime pointer evidence, and symbol bundle context in one agent workflow.</p></article>
            <article class="mode-card"><h3>Quality improvement</h3><p>Add cross-file dependency expansion, deterministic execution for arithmetic/string tasks, and cached symbol bundles.</p></article>
            <article class="mode-card"><h3>Future evaluation</h3><p>Repeat Self-Extend with a build that exposes group attention consistently across perplexity, passkey, and code tasks.</p></article>
          </div>
        </div>`
    }
  ]
};
