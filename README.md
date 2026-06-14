# KTU Portal TUI

A personal terminal client for the APJ Abdul Kalam Technological University
e-Governance portal (app.ktu.edu.in).

## Features

* Form-based login with CSRF + session handling
* Dashboard, Profile, Exam definitions, Pending results, Student details
* Sidenav-driven TUI with fixed header, sidebar, and status bar (v0.4)
* Page-aware sub-links: shows the sidebar links extracted from each page
* Rate-limited (1 req/s, burst 3) to be polite to the AWS ALB
* Offline preview mode (preview_screens.py) — no live network needed

## Install

```
pip install -r requirements.txt
```

## Run

```
cd src
python3 ktu_tui.py             # interactive TUI
python3 ktu_tui.py --version
python3 ktu_tui.py --probe     # public endpoint inventory
python3 ktu_tui.py --check-pages   # test parser against saved HTML
```

## Layout

```
+- KTU STUDENT PORTAL -  Online  app.ktu.edu.in  Welcome NAME -+  header
+------+--------------------------------+
| Menu |  content (rendered PageSnapshot)|
|  1 D |                                  |
|  2 E |                                  |
|  3 P |                                  |
+------+--------------------------------+
| Ready | F5 refresh L login B back Q quit|  status
+------+--------------------------------+
```

## Files

| File | Purpose |
|------|---------|
| src/ktu_tui.py | TUI entry point, header/sidenav/content/statusbar layout |
| src/ktu_client.py | HTTP client with rate limiter, CSRF, session-expiry detection |
| src/ktu_parser.py | HTML -> PageSnapshot (welcome, panels, KV, tables, alerts, sidebar links) |
| src/preview_screens.py | Offline screen preview (no network) |
| src/ktu_tui_v0.py | Original v0.1 script (archived) |
| docs/architecture.md | Full architecture report |
| debug/pages/*.html | Saved HTML pages used to build the parser |

## See also

docs/architecture.md - full system architecture
