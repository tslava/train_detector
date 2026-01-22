#!/usr/bin/env python3
"""
Train detector (callback-based) for macOS microphone.
- Detects a "train" if smoothed audio level >= THRESHOLD_DBFS is sustained for >= MIN_DURATION_S.
- Resilient to buffer overflow (uses callback + increased latency).
- Event logs in CSV (convenient for Google Sheets). Optionally logs continuous levels to CSV.

Python 3.12+
"""

import csv
import os
import sys
import time
import queue
from datetime import datetime
import numpy as np
import sounddevice as sd

# ============ CONFIG ============
SAMPLE_RATE = 44100          # 44.1 kHz (more stable on Mac)
CHANNELS = 1
# If 0, PortAudio will choose the optimal callback buffer size automatically.
CALLBACK_BLOCKSIZE = 0
# IMPORTANT: high latency gives larger internal buffer => fewer overflows.
LATENCY = "high"             # can also be a number in seconds, e.g. 0.2
# Smoothing/detection
SMOOTH_SEC = 3.0
THRESHOLD_DBFS = -15.0
MIN_DURATION_S = 30.0
HYSTERESIS_DB = 2.0
STOP_HOLD_S = 5.0
# Logs
EVENTS_CSV = "train_events.csv"
WRITE_LEVELS_CSV = False
LEVELS_CSV = "noise_levels.csv"
# Input device (None = default, or index/substring of device name)
INPUT_DEVICE = None
# ============ /CONFIG ===========

# Queue from callback -> main thread: (rms_block, frames, timestamp)
q = queue.Queue(maxsize=1000)
overflow_count = 0

def dbfs_from_rms(rms: float) -> float:
    rms = max(float(rms), 1e-12)
    return 20.0 * np.log10(rms)

def ensure_csv_header(path: str, header: list[str]) -> None:
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    if new_file:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def pick_input_device(spec=None):
    if spec is None:
        return None
    devices = sd.query_devices()
    if isinstance(spec, int):
        return spec
    key = str(spec).lower()
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0 and key in str(d.get("name", "")).lower():
            return i
    print(f"[WARN] Device matching '{spec}' not found, using system default.")
    return None

def audio_callback(indata, frames, time_info, status):
    global overflow_count
    # Don't print frequently - just count.
    if status and status.input_overflow:
        overflow_count += 1

    # indata: float32, shape (frames, channels)
    if indata.ndim == 2 and indata.shape[1] > 1:
        mono = np.mean(indata, axis=1, dtype=np.float32)
    else:
        mono = indata.reshape(-1)

    # Block RMS
    rms = float(np.sqrt(np.mean(mono * mono) + 1e-12))
    ts = datetime.now().astimezone()
    try:
        q.put_nowait((rms, frames, ts))
    except queue.Full:
        # If main thread is busy, silently drop the block.
        pass

def main():
    device_index = pick_input_device(INPUT_DEVICE)

    ensure_csv_header(EVENTS_CSV, [
        "start_time_local", "end_time_local", "duration_s",
        "avg_dbfs", "peak_dbfs", "threshold_dbfs", "blocks"
    ])
    if WRITE_LEVELS_CSV:
        ensure_csv_header(LEVELS_CSV, ["time_local", "dbfs_block", "dbfs_smooth", "threshold_dbfs", "status"])

    threshold_high = THRESHOLD_DBFS
    threshold_low = THRESHOLD_DBFS - HYSTERESIS_DB

    # Detector state
    ema_rms = None
    # For dynamic alpha, use actual block duration from callback
    def alpha_for(block_sec: float) -> float:
        # Guard against extreme values
        return min(1.0, max(0.001, block_sec / max(0.5, SMOOTH_SEC)))

    candidate_above_since_wall = None
    candidate_above_since_mono = None

    event_active = False
    event_start_wall = None
    event_start_mono = None
    last_above_mono = None

    event_blocks = 0
    event_sum_rms = 0.0
    event_peak_rms = 0.0

    print("[INFO] Started. Press Ctrl+C to exit.")
    print(f"[INFO] Threshold {THRESHOLD_DBFS} dBFS, minimum {MIN_DURATION_S}s, hysteresis {HYSTERESIS_DB} dB")
    if device_index is not None:
        print(f"[INFO] Device: {device_index}")
    print(f"[INFO] SAMPLE_RATE={SAMPLE_RATE}, LATENCY={LATENCY}, CALLBACK_BLOCKSIZE={CALLBACK_BLOCKSIZE}")

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            device=device_index,
            latency=LATENCY,
            blocksize=CALLBACK_BLOCKSIZE,
            callback=audio_callback,
        ):
            last_overflow_report = time.monotonic()
            while True:
                try:
                    rms, frames, t_wall = q.get(timeout=1.0)
                except queue.Empty:
                    # Periodically show overflow count if any
                    now = time.monotonic()
                    if overflow_count and now - last_overflow_report > 5:
                        print(f"[WARN] Input overflows: {overflow_count} (check LATENCY and CPU load)")
                        overflow_count = 0
                        last_overflow_report = now
                    continue

                block_sec = frames / float(SAMPLE_RATE)
                a = alpha_for(block_sec)

                # EMA
                if ema_rms is None:
                    ema_rms = rms
                else:
                    ema_rms = (1.0 - a) * ema_rms + a * rms

                block_db = dbfs_from_rms(rms)
                smooth_db = dbfs_from_rms(ema_rms)

                t_mono = time.monotonic()
                status = "idle"

                if not event_active:
                    if smooth_db >= threshold_high:
                        if candidate_above_since_mono is None:
                            candidate_above_since_mono = t_mono
                            candidate_above_since_wall = t_wall
                        if (t_mono - candidate_above_since_mono) >= MIN_DURATION_S:
                            event_active = True
                            event_start_mono = candidate_above_since_mono
                            event_start_wall = candidate_above_since_wall
                            last_above_mono = t_mono
                            event_blocks = 0
                            event_sum_rms = 0.0
                            event_peak_rms = 0.0
                            status = "train_active"
                    else:
                        candidate_above_since_mono = None
                        candidate_above_since_wall = None
                else:
                    event_blocks += 1
                    event_sum_rms += ema_rms
                    if ema_rms > event_peak_rms:
                        event_peak_rms = ema_rms

                    if smooth_db >= threshold_low:
                        last_above_mono = t_mono

                    if last_above_mono is not None and (t_mono - last_above_mono) >= STOP_HOLD_S:
                        event_active = False
                        end_wall = t_wall
                        duration_s = max(0.0, t_mono - (event_start_mono or t_mono))
                        avg_rms = event_sum_rms / max(1, event_blocks)
                        avg_db = dbfs_from_rms(avg_rms)
                        peak_db = dbfs_from_rms(max(1e-12, event_peak_rms))

                        with open(EVENTS_CSV, "a", newline="", encoding="utf-8") as f:
                            csv.writer(f).writerow([
                                event_start_wall.isoformat(timespec="seconds"),
                                end_wall.isoformat(timespec="seconds"),
                                f"{duration_s:.1f}",
                                f"{avg_db:.1f}",
                                f"{peak_db:.1f}",
                                f"{THRESHOLD_DBFS:.1f}",
                                event_blocks
                            ])

                        print(f"[EVENT] Train: {event_start_wall.isoformat(timespec='seconds')} -> "
                              f"{end_wall.isoformat(timespec='seconds')}, {duration_s:.1f}s, "
                              f"avg {avg_db:.1f}, peak {peak_db:.1f}")
                        candidate_above_since_mono = None
                        candidate_above_since_wall = None
                    else:
                        status = "train_active"

                if WRITE_LEVELS_CSV:
                    with open(LEVELS_CSV, "a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerow([
                            t_wall.isoformat(timespec="seconds"),
                            f"{block_db:.1f}",
                            f"{smooth_db:.1f}",
                            f"{THRESHOLD_DBFS:.1f}",
                            status
                        ])

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
