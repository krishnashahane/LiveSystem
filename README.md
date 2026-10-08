# LiveSystem

A real-time terminal system monitor for Linux, macOS, and Windows. It uses **psutil** for system telemetry and **Rich** for the terminal dashboard.

## What it monitors

- CPU utilization, per-core usage, frequency, and load average when the OS exposes it
- RAM and swap usage
- Network TX/RX rates, totals, packets, errors, drops, and connection counts when permission allows
- Top processes by CPU usage
- Mounted disk usage and aggregate disk I/O
- Basic GPU identification on macOS
- macOS CPU thermal level when the platform exposes it

GPU utilization is intentionally reported as unavailable because `psutil` does not provide a portable GPU-utilization API. The dashboard does not pretend to have telemetry it cannot reliably obtain.

## Requirements

- Python 3.9+
- A terminal with Unicode support
- macOS, Linux, or Windows

The project has only two runtime dependencies, pinned to the tested/current releases used by this repository: `psutil==7.2.2` and `rich==15.0.0`. citeturn424355search0turn424355search1

## Installation

Clone the repository and enter the project directory:

```bash
git clone https://github.com/krishnashahane/LiveSystem.git
cd LiveSystem
```

Create and activate a virtual environment:

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the pinned dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```bash
python monitor.py
```

Stop with `Ctrl+C`.

## Security and reliability

LiveSystem is a local monitoring application. It does not open a network server, accept remote commands, execute shell input supplied by users, or persist credentials.

Platform-specific system commands are executed only when required and are invoked with fixed argument lists rather than shell strings. Unsupported metrics degrade gracefully instead of being fabricated.

Dependencies are pinned in `requirements.txt` so installs are reproducible and do not silently pull arbitrary newer releases. The repository currently uses releases newer than the historical psutil versions affected by CVE-2019-18874. citeturn693337search3turn424355search0

## Project structure

```text
LiveSystem/
├── monitor.py
├── requirements.txt
├── README.md
└── LICENSE
```

## Troubleshooting

### Permission errors

Some operating systems restrict process and network connection inspection. LiveSystem catches those permission failures and continues with the metrics it can access.

### No GPU utilization

This is expected. GPU utilization is not exposed through the portable psutil API, so LiveSystem shows the GPU identity when available rather than reporting an unreliable value.

### Terminal rendering issues

Use a modern UTF-8 terminal. If the display is corrupted, try a standard terminal application and ensure your terminal font supports the dashboard characters.

## License

MIT
