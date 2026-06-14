# KTU Portal TUI

Terminal client for the APJ Abdul Kalam Technological University
e-Governance portal ([app.ktu.edu.in](https://app.ktu.edu.in)).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
pip install -r requirements.txt
```

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

See `docs/architecture.md` for full architecture and server interaction details.
