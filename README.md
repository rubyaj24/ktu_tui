# KTU Portal TUI

I built this terminal client for the APJ Abdul Kalam Technological University
e-Governance portal ([app.ktu.edu.in](https://app.ktu.edu.in))
because I wanted a faster way to check my results, profile, and exam schedules
without clicking through the web interface.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
pip install -r requirements.txt
```

> **Windows:** My raw key reader has a Windows branch (`msvcrt`), but I
> only test on Linux. You may need to adjust terminal handling.

## Run

```bash
cd src
python3 ktu_tui.py
```

| Key | Action |
|-----|--------|
| `↑` `↓` | Navigate |
| `Enter` | Select |
| `r` | Refresh |
| `b` | Back |
| `l` | Re-login |
| `q` | Quit |

## Project

```
src/
├── ktu_tui.py          # TUI entry point
├── ktu_input.py        # Key reader
├── ktu_client.py       # HTTP client
├── ktu_parser.py       # HTML parser
└── preview_screens.py  # Offline preview
```

I put all architecture and server-interaction details in `docs/architecture.md`.
