# Train Detector

**Counts the trains passing your window, using nothing but a Mac microphone.** It tracks the ambient sound level in real time, recognises a train as a sustained rise above a threshold and appends each event (start, end, duration, average and peak level) to a CSV you can chart in any spreadsheet.

```bash
uv sync
uv run python main.py   # Ctrl+C to stop
```

**Stack:** Python 3.12 · sounddevice (PortAudio) · NumPy · uv

## Why?

If you live near train tracks and want to track train frequency, duration, or noise levels over time, this tool provides a simple way to collect that data automatically. The CSV output works well with Google Sheets for visualization and analysis.

## Requirements

- macOS with microphone access
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
git clone https://github.com/tslava/train_detector.git
cd train_detector
uv sync
```

## Usage

```bash
uv run python main.py
```

Press `Ctrl+C` to stop.

On first run, macOS will prompt for microphone access permission.

## Configuration

Edit constants at the top of `main.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `THRESHOLD_DBFS` | -15 | Detection threshold in dBFS. Lower values = more sensitive |
| `MIN_DURATION_S` | 30 | Minimum sustained duration (seconds) before triggering an event |
| `HYSTERESIS_DB` | 2 | Hysteresis band (dB) to prevent rapid on/off switching |
| `STOP_HOLD_S` | 5 | Hold time (seconds) before ending event after signal drops |
| `SMOOTH_SEC` | 3 | EMA smoothing window (seconds) |
| `WRITE_LEVELS_CSV` | False | Enable continuous level logging to `noise_levels.csv` |
| `INPUT_DEVICE` | None | Audio input device (None = system default) |

## Output

Detected events are logged to `train_events.csv`:

```csv
start_time_local,end_time_local,duration_s,avg_dbfs,peak_dbfs,threshold_dbfs,blocks
2025-08-18T17:19:17+02:00,2025-08-18T17:19:33+02:00,16.4,-36.4,-32.8,-35.0,1861
```

| Column | Description |
|--------|-------------|
| `start_time_local` | Event start time (ISO 8601 with timezone) |
| `end_time_local` | Event end time |
| `duration_s` | Event duration in seconds |
| `avg_dbfs` | Average audio level during event |
| `peak_dbfs` | Peak audio level during event |
| `threshold_dbfs` | Threshold setting used |
| `blocks` | Number of audio blocks processed |

## How It Works

1. **Audio capture**: Uses `sounddevice` with PortAudio callback for real-time microphone input
2. **Signal processing**: Calculates RMS levels with exponential moving average (EMA) smoothing
3. **Event detection**: Hysteresis-based threshold detection requiring sustained levels above threshold for the minimum duration before triggering
4. **Logging**: Events are appended to CSV for later analysis

## License

[MIT](LICENSE)

---

Built by [Wiaczeslaw Cyunczyk](https://tslava.dev)
