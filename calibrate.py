#!/usr/bin/env python3
"""
Voice calibration recorder — capture real samples in your own voice/mic so the
streaming silence detection and accuracy can be tuned to you.

Run it in a terminal from the repo:   .venv/bin/python calibrate.py
Press ENTER to start each clip, speak, press ENTER again to stop. Ctrl-C to quit
early. Files land in ~/.nova/calibration/ ; tell Claude when they're recorded.
"""
import json
import os
import subprocess
import threading
import wave
from datetime import datetime

OUT = os.path.expanduser("~/.nova/calibration")
os.makedirs(OUT, exist_ok=True)

PROMPTS = [
    ("short", "A short command, e.g.: \"Hey Pixel Bot, what's the server disk usage right now?\""),
    ("pauses", "A few requests with a clear PAUSE between each: "
               "\"Check the disk usage.\" ... pause ... \"Then tomorrow's weather.\" ... pause ... \"Then my meetings.\""),
    ("normal", "A normal request, the way you'd actually say it — a couple of sentences, natural pace."),
    ("long", "Ramble freely for ~2-3 minutes about anything, with natural pauses, so we can test long takes."),
]


def record(path: str) -> float:
    proc = subprocess.Popen(
        ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE,
    )
    buf = bytearray()
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            data = proc.stdout.read(4096)
            if not data:
                break
            buf.extend(data)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    input()  # ENTER stops
    stop.set()
    proc.terminate()
    proc.wait()
    t.join(timeout=1)

    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(bytes(buf))
    return (len(buf) // 2) / 16000.0


def main():
    print("=" * 64)
    print("  NOVA VOICE CALIBRATION")
    print("  ENTER = start, ENTER = stop. Ctrl-C to quit early.")
    print("=" * 64)
    manifest = []
    try:
        for key, prompt in PROMPTS:
            print("\n" + "-" * 64)
            print(f"[{key}]  {prompt}")
            input("\nPress ENTER to START...")
            print(">>> RECORDING — press ENTER when done <<<")
            ts = datetime.now().strftime("%H%M%S")
            path = os.path.join(OUT, f"{key}_{ts}.wav")
            dur = record(path)
            print(f"  saved: {path}  ({dur:.1f}s)")
            manifest.append({"key": key, "prompt": prompt, "file": path, "dur": round(dur, 1)})
    except KeyboardInterrupt:
        print("\n(stopped early)")

    if manifest:
        with open(os.path.join(OUT, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"\nDone — {len(manifest)} clip(s) in {OUT}")
        print("Tell Claude they're ready.")


if __name__ == "__main__":
    main()
