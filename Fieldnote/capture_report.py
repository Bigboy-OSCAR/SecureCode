"""Print a reproducible field recorder bench report using simulated meter samples."""

import json
import random
from pathlib import Path


def main():
    settings = Path(__file__).parent / "reference" / "recorder.json"
    recorder = json.loads(settings.read_text(encoding="utf-8"))
    survey = recorder["survey"]
    meter = random.Random(48)
    count = 0
    loudest = -60
    for track_id in survey["track_ids"]:
        for window in range(1, survey["windows_per_track"] + 1):
            peak = meter.randint(-30, -3)
            count += 1
            loudest = max(loudest, peak)
            print(f"METER track={track_id} window={window:02d} peak_dbfs={peak} kit={recorder['kit']}")
    print(f"CAPTURE_SUMMARY windows={count} loudest_dbfs={loudest} kit={recorder['kit']}")


if __name__ == "__main__":
    main()
