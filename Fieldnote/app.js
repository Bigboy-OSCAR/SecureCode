"use strict";

const sampleRate = 22050;
const duration = 6;
const storageKey = "fieldnote.reviewed.v1";
const byId = id => document.getElementById(id);
const wave = byId("waveform");
const playButton = byId("play");
const previewColors = {
  birds: ["#dce8cd", "#446644"], waves: ["#d4e3de", "#416456"],
  crossing: ["#eedcc8", "#8a583e"], rain: ["#dce1ed", "#546580"]
};
let selected = recordings[0];
let habitat = "전체";
let reviewed = new Set();
let context, source, frame, startedAt;

try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
  if (Array.isArray(saved)) reviewed = new Set(saved.filter(id => recordings.some(row => row.id === id)));
} catch {
  byId("status").textContent = "저장한 검토 상태를 열 수 없어 새로 시작합니다.";
}

// Each preview's waveform and playback are derived from the same mono samples.
function synthesize(record) {
  const audio = new Float32Array(sampleRate * duration);
  let random = record.seed, air = 0, peak = 0;
  for (let n = 0; n < audio.length; n++) {
    const t = n / sampleRate;
    random = (Math.imul(1664525, random) + 1013904223) >>> 0;
    air = .94 * air + .06 * (2 * random / 4294967296 - 1);
    let tone;
    if (record.sound === "birds") {
      const beat = t % .83;
      const chirp = Math.sin(2 * Math.PI * (1450 * beat + 800 * beat * beat));
      tone = air * .43 + chirp * Math.exp(-90 * (beat - .19) ** 2) * (.48 + .26 * Math.sin(2.7 * t));
    } else if (record.sound === "waves") {
      const swell = Math.exp(-3 * (t - 1.4) ** 2) + 1.65 * Math.exp(-2.2 * (t - 4.1) ** 2);
      tone = air * (.1 + swell);
    } else if (record.sound === "crossing") {
      const beat = t % .7;
      tone = .35 * air + .55 * Math.sin(2 * Math.PI * 740 * t) * Math.exp(-160 * (beat - .14) ** 2);
    } else {
      const beat = t % .51;
      const pitch = 460 + 130 * Math.sin(Math.floor(t / .51) * 2);
      tone = air * .6 + .47 * Math.sin(2 * Math.PI * pitch * beat) * Math.exp(-22 * beat);
    }
    audio[n] = tone * Math.min(1, t / .04, (duration - t) / .08);
    peak = Math.max(peak, Math.abs(audio[n]));
  }
  const gain = 10 ** (record.peakDb / 20) / peak;
  for (let n = 0; n < audio.length; n++) audio[n] *= gain;
  return audio;
}

function envelope(samples, columns) {
  const bars = [];
  for (let i = 0; i < columns; i++) {
    let peak = 0;
    const end = Math.floor((i + 1) * samples.length / columns);
    for (let n = Math.floor(i * samples.length / columns); n < end; n++) peak = Math.max(peak, Math.abs(samples[n]));
    bars.push(peak);
  }
  const max = Math.max(...bars);
  return bars.map(value => value / max);
}

const audioCache = new Map(recordings.map(record => {
  const samples = synthesize(record);
  return [record.id, { samples, bars: envelope(samples, 240), mini: envelope(samples, 19) }];
}));

function drawBars(canvas, values, color, progress, grid) {
  const bounds = canvas.getBoundingClientRect();
  const w = bounds.width, h = bounds.height, ratio = window.devicePixelRatio || 1;
  if (!w || !h) return;
  if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
  }
  const pen = canvas.getContext("2d");
  pen.setTransform(ratio, 0, 0, ratio, 0, 0);
  pen.clearRect(0, 0, w, h);
  if (grid) {
    pen.fillStyle = "#355648";
    for (let i = 1; i < 12; i++) pen.fillRect(i * w / 12, 0, 1, h);
    for (let i = 1; i < 4; i++) pen.fillRect(0, i * h / 4, w, 1);
  }
  const step = w / values.length;
  values.forEach((value, i) => {
    pen.fillStyle = progress > 0 && i / values.length < progress ? "#f2c67c" : color;
    const height = Math.max(1.5, value * h * .88);
    pen.fillRect(i * step, (h - height) / 2, Math.max(1, step * .72), height);
  });
  if (progress > 0) {
    pen.fillStyle = "#f7e0ac";
    pen.fillRect(Math.min(progress, 1) * (w - 2), 0, 2, h);
  }
}

function showWave(seconds = 0) {
  byId("elapsed").textContent = "00:0" + Math.floor(seconds);
  drawBars(wave, audioCache.get(selected.id).bars, "#aaca8c", seconds / duration, true);
}

function stopPlayback() {
  cancelAnimationFrame(frame);
  if (source) {
    source.onended = null;
    source.stop();
    source.disconnect();
    source = null;
  }
  playButton.setAttribute("aria-pressed", "false");
  byId("play-label").textContent = "샘플 재생";
  showWave();
}

playButton.addEventListener("click", async () => {
  if (source) { stopPlayback(); return; }
  playButton.disabled = true;
  const record = selected;
  try {
    context ??= new AudioContext();
    await context.resume();
    if (record !== selected) return;
    const samples = audioCache.get(record.id).samples;
    const buffer = context.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(samples, 0);
    source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    source.onended = stopPlayback;
    startedAt = context.currentTime;
    source.start();
    playButton.setAttribute("aria-pressed", "true");
    byId("play-label").textContent = "재생 정지";
    function tick() {
      showWave(Math.min(duration, context.currentTime - startedAt));
      frame = requestAnimationFrame(tick);
    }
    tick();
  } catch {
    stopPlayback();
    byId("status").textContent = "오디오를 재생할 수 없습니다. 브라우저의 오디오 출력을 확인하세요.";
  } finally { playButton.disabled = false; }
});

function showDetails() {
  const hot = classifyPeak(selected.peakDb) === "hot";
  byId("track-id").textContent = selected.id;
  byId("track-title").textContent = selected.title;
  byId("track-location").textContent = [selected.place, selected.date, selected.time].join("  /  ");
  byId("note").textContent = selected.note;
  byId("peak").textContent = (hot ? "레벨 주의" : "레벨 안정") + " · " + selected.peakDb + " dBFS";
  byId("peak").classList.toggle("hot", hot);
  byId("reviewed").checked = reviewed.has(selected.id);
  byId("review-count").textContent = reviewed.size + " / " + recordings.length;
  showWave();
}

function visibleRecords() {
  return recordings.filter(row => habitat === "전체" || row.habitat === habitat);
}

const recordButtons = new Map();
for (const record of recordings) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "record";
  button.innerHTML = '<span class="swatch"><canvas aria-hidden="true"></canvas></span><span class="record-copy"><span class="record-id"></span><strong></strong></span><span class="record-state"></span>';
  button.querySelector(".swatch").style.backgroundColor = previewColors[record.sound][0];
  button.querySelector(".record-id").textContent = record.id + " · " + record.habitat;
  button.querySelector("strong").textContent = record.title;
  button.addEventListener("click", () => {
    stopPlayback();
    selected = record;
    showDetails();
    showList();
  });
  byId("records").append(button);
  recordButtons.set(record.id, button);
}

function showList() {
  const visible = visibleRecords();
  byId("result-count").textContent = visible.length + "개 기록";
  for (const row of recordings) {
    const button = recordButtons.get(row.id);
    button.hidden = !visible.includes(row);
    button.setAttribute("aria-pressed", String(row === selected));
    const state = button.querySelector(".record-state");
    state.textContent = reviewed.has(row.id) ? "✓" : "";
    state.setAttribute("aria-label", reviewed.has(row.id) ? "검토 완료" : "");
    if (!button.hidden) drawBars(button.querySelector("canvas"), audioCache.get(row.id).mini, previewColors[row.sound][1], 0, false);
  }
}

for (const name of ["전체", ...new Set(recordings.map(row => row.habitat))]) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = name;
  button.setAttribute("aria-pressed", String(name === habitat));
  button.addEventListener("click", () => {
    stopPlayback();
    habitat = name;
    for (const option of byId("filters").children) option.setAttribute("aria-pressed", String(option === button));
    if (!visibleRecords().includes(selected)) selected = visibleRecords()[0];
    showDetails();
    showList();
  });
  byId("filters").append(button);
}

byId("reviewed").addEventListener("change", event => {
  if (event.target.checked) reviewed.add(selected.id);
  else reviewed.delete(selected.id);
  try {
    localStorage.setItem(storageKey, JSON.stringify([...reviewed]));
  } catch {
    byId("status").textContent = "현재 창에 검토 상태를 표시했습니다. 브라우저가 영구 저장을 허용하지 않습니다.";
  }
  byId("review-count").textContent = reviewed.size + " / " + recordings.length;
  showList();
});

window.addEventListener("resize", () => {
  if (!source) showWave();
  showList();
});
showDetails();
showList();
playButton.disabled = false;
