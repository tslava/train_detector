# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Train detector application that uses macOS microphone input to detect passing trains based on sustained audio levels. Events are logged to CSV for analysis (e.g., Google Sheets).

## Running the Application

```bash
# Install dependencies (uses uv)
uv sync

# Run the detector
uv run python main.py
```

Press Ctrl+C to stop.

## Architecture

Single-file application (`main.py`) with callback-based audio processing:

1. **Audio capture**: Uses `sounddevice` with PortAudio callback to capture microphone input
2. **Signal processing**: Calculates RMS levels with exponential moving average (EMA) smoothing
3. **Event detection**: Hysteresis-based threshold detection requiring sustained levels above threshold for MIN_DURATION_S before triggering
4. **Logging**: Events written to `train_events.csv`; optional continuous levels to `noise_levels.csv`

## Key Configuration (in main.py)

- `THRESHOLD_DBFS`: Detection threshold in dBFS (default -15)
- `MIN_DURATION_S`: Minimum sustained duration to trigger event (default 30s)
- `HYSTERESIS_DB`: Hysteresis band to prevent rapid on/off (default 2 dB)
- `STOP_HOLD_S`: Hold time before ending event after signal drops (default 5s)
- `SMOOTH_SEC`: EMA smoothing window (default 3s)
- `WRITE_LEVELS_CSV`: Enable continuous level logging (default False)

## Dependencies

- Python 3.12+
- numpy, sounddevice, openpyxl
