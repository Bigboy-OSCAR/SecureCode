window.PresentationData = {
  colors: {
    baseline: "#c9544d",
    oracle: "#138078",
    select: "#2f6fc0",
    bundle: "#7057c8",
    line: "#3f8b4c",
    file: "#e4aa32"
  },
  charts: {
    baselineRawTokens: {
      scale: "log",
      valueSuffix: " tok",
      rows: [
        { label: "source full", value: 120208, color: "#c9544d" },
        { label: "runtime full", value: 131136, color: "#c9544d" },
        { label: "symbol full repo", value: 67188, color: "#c9544d" },
        { label: "self code input", value: 4854, color: "#e4aa32" }
      ]
    },
    sourceAccuracy: {
      valueSuffix: "%",
      rows: [
        { label: "full_source", value: 33.3, color: "#c9544d" },
        { label: "pointer_oracle", value: 100, color: "#138078" },
        { label: "pointer_select", value: 100, color: "#2f6fc0" }
      ]
    },
    sourceTokens: {
      scale: "log",
      valueSuffix: " tok",
      rows: [
        { label: "full_source", value: 120208, color: "#c9544d" },
        { label: "pointer_oracle", value: 286, color: "#138078" },
        { label: "pointer_select", value: 780, color: "#2f6fc0" }
      ]
    },
    sourceWall: {
      valueSuffix: " s",
      rows: [
        { label: "full_source", value: 22.117, color: "#c9544d" },
        { label: "pointer_oracle", value: 2.443, color: "#138078" },
        { label: "pointer_select", value: 6.423, color: "#2f6fc0" }
      ]
    },
    runtimeAccuracy: {
      valueSuffix: "%",
      rows: [
        { label: "full_runtime", value: 33.3, color: "#c9544d" },
        { label: "pointer_oracle", value: 100, color: "#138078" },
        { label: "pointer_select", value: 100, color: "#2f6fc0" }
      ]
    },
    runtimeTokens: {
      scale: "log",
      valueSuffix: " tok",
      rows: [
        { label: "full_runtime", value: 131136, color: "#c9544d" },
        { label: "pointer_oracle", value: 311, color: "#138078" },
        { label: "pointer_select", value: 757, color: "#2f6fc0" }
      ]
    },
    runtimeWall: {
      valueSuffix: " s",
      rows: [
        { label: "full_runtime", value: 26.27, color: "#c9544d" },
        { label: "pointer_oracle", value: 2.61, color: "#138078" },
        { label: "pointer_select", value: 6.891, color: "#2f6fc0" }
      ]
    },
    symbolEasyWall: {
      scale: "log",
      valueSuffix: " s",
      rows: [
        { label: "full_repo", value: 612.869, color: "#c9544d" },
        { label: "full_file", value: 2.286, color: "#e4aa32" },
        { label: "line_span", value: 2.12, color: "#3f8b4c" },
        { label: "symbol_oracle", value: 2.131, color: "#138078" },
        { label: "symbol_select", value: 181.191, color: "#2f6fc0" }
      ]
    },
    symbolEasyTokens: {
      scale: "log",
      valueSuffix: " tok",
      rows: [
        { label: "full_repo", value: 67188, color: "#c9544d" },
        { label: "full_file", value: 256, color: "#e4aa32" },
        { label: "line_span", value: 199, color: "#3f8b4c" },
        { label: "symbol_oracle", value: 199, color: "#138078" },
        { label: "symbol_select", value: 33871, color: "#2f6fc0" }
      ]
    },
    symbolHardAccuracy: {
      valueSuffix: "%",
      rows: [
        { label: "single symbol", value: 0, color: "#c9544d" },
        { label: "full_file", value: 33.3, color: "#e4aa32" },
        { label: "bundle oracle", value: 33.3, color: "#138078" },
        { label: "filtered bundle", value: 33.3, color: "#7057c8" }
      ]
    },
    symbolSelectorImprovement: {
      scale: "log",
      valueSuffix: " tok",
      rows: [
        { label: "old selector", value: 33922, color: "#c9544d" },
        { label: "filtered bundle", value: 587, color: "#7057c8" }
      ]
    },
    selfPasskey: {
      valueSuffix: "%",
      rows: [
        { label: "off baseline", value: 66.7, color: "#e4aa32" },
        { label: "G=2", value: 0, color: "#c9544d" },
        { label: "G=4", value: 0, color: "#c9544d" }
      ]
    },
    selfContextCapacity: {
      valueSuffix: " ctx",
      rows: [
        { label: "off", value: 4320, color: "#e4aa32" },
        { label: "G=2", value: 8416, color: "#2f6fc0" },
        { label: "G=4", value: 16608, color: "#7057c8" }
      ]
    },
    selfCodeAssist: {
      valueSuffix: "%",
      rows: [
        { label: "off", value: 0, color: "#c9544d" },
        { label: "G=2", value: 0, color: "#c9544d" },
        { label: "G=4", value: 0, color: "#c9544d" }
      ]
    },
    selfPpl: {
      scale: "log",
      valueSuffix: " PPL",
      rows: [
        { label: "Q4 ctx2048", value: 7.8529, color: "#138078" },
        { label: "Q5 ctx2048", value: 7.8592, color: "#138078" },
        { label: "Q4 ctx4096", value: 304.6347, color: "#c9544d" },
        { label: "Q5 ctx4096", value: 309.3053, color: "#c9544d" }
      ]
    },
    overallPrompt: {
      scale: "log",
      valueSuffix: " tok",
      rows: [
        { label: "source full", value: 120208, color: "#c9544d" },
        { label: "source select", value: 780, color: "#2f6fc0" },
        { label: "runtime full", value: 131136, color: "#c9544d" },
        { label: "runtime select", value: 757, color: "#2f6fc0" },
        { label: "symbol full repo", value: 67188, color: "#c9544d" },
        { label: "filtered bundle", value: 587, color: "#7057c8" }
      ]
    }
  }
};
