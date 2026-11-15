// Peak level is measured in dBFS. A sample at the threshold needs attention.
function classifyPeak(peakDb) {
  return peakDb >= -6 ? "hot" : "normal";
}

const recordings = [
  {
    id: "FN-01", title: "솔숲의 첫 새소리", habitat: "숲", place: "강릉 · 경포 솔숲",
    time: "05:42", date: "2026.09.12", peakDb: -12, sound: "birds", seed: 17,
    note: "낮게 깔린 바람 위로 짧은 지저귐이 번갈아 들린다. 음 사이의 빈 공간에 귀를 기울여 보자."
  },
  {
    id: "FN-02", title: "방파제의 잔물결", habitat: "물가", place: "속초 · 외옹치항",
    time: "07:18", date: "2026.09.13", peakDb: -6, sound: "waves", seed: 31,
    note: "서로 다른 길이의 물결이 겹치며 천천히 부풀었다 잦아든다. 두 번째 너울에서 가장 큰 파형을 찾을 수 있다."
  },
  {
    id: "FN-03", title: "건널목의 저녁 신호", habitat: "도시", place: "서울 · 성수동",
    time: "18:26", date: "2026.09.15", peakDb: -4, sound: "crossing", seed: 47,
    note: "낮은 거리 소음 위로 일정한 간격의 신호음이 이어진다. 반복되는 봉우리에서 소리의 간격을 읽어 보자."
  },
  {
    id: "FN-04", title: "연못에 닿는 빗방울", habitat: "물가", place: "구례 · 연못가",
    time: "14:07", date: "2026.09.17", peakDb: -16, sound: "rain", seed: 71,
    note: "부드러운 빗소리에 둥근 물방울 소리가 하나씩 떠오른다. 물방울마다 음높이가 조금씩 달라진다."
  }
];
