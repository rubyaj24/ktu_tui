# KTU Portal TUI — Architecture Report

**Project:** Personal terminal client for the KTU e-Governance portal
**Target:** https://app.ktu.edu.in
**Date:** 2026-06-14
**Status:** v0.4.0 — functional TUI

**Source code:** `src/ktu_tui.py` (entry point), `src/ktu_client.py` (HTTP), `src/ktu_parser.py` (HTML), `src/preview_screens.py` (offline preview)

---

## 1. Executive summary

KTU’s e-Gov portal is a **server-rendered Java Spring MVC web application**
served behind an **AWS Application Load Balancer (ALB)**. It exposes features
as **HTML pages** under the URL pattern `/eu/<module>/<verb>.htm`, with no
public JSON API. All data is embedded in HTML; a personal TUI must therefore
**scrape and parse** the rendered DOM.

The TUI in this project uses a session cookie (`JSESSIONID`) obtained via form
login, fetches the relevant `.htm` pages, and converts their **Bootstrap 3
list-groups** and **tables** into rich terminal renderables.

---

## 2. Stack fingerprint

| Layer   | Finding |
|---------|---------|
| Server  | Spring MVC (Java) — inferred from `JSESSIONID` + `.htm` pattern |
| LB      | AWS ALB — `Set-Cookie: AWSALB`, `AWSALBCORS` |
| TLS     | AWS ACM |
| Frontend| jQuery 1.11.3, Bootstrap 3 (older but functional) |
| Auth    | Form-based login with `CSRF_TOKEN` hidden field |
| Session | Cookie-based (`JSESSIONID` + `AWSALB*`) |
| API     | None public — data is server-rendered HTML |

---

## 3. URL routing convention

Three-tier module path: `https://app.ktu.edu.in/eu/<module>/<verb>.htm`

Public modules: `anon` (about, FAQ, contact, research registration)
Authenticated modules: `alt` (dashboard), `stu` (student profile), `exm` (exams), `res` (results)
First segment after `/eu/` is the module code; second is the action.

---

## 4. Login flow

1. GET `https://app.ktu.edu.in/login.htm` — receive `JSESSIONID` cookie + parse `CSRF_TOKEN` from hidden input
2. POST same URL with `username`, `password`, `CSRF_TOKEN`
3. Server validates; on success returns dashboard HTML and a fresh `JSESSIONID`
4. **Verify**: GET `/eu/alt/dashboard.htm` — must NOT redirect to login
5. Authenticated pages expose `<span class="tooltiptext">Welcome NAME</span>` in the navbar

**Critical detection rule:** the login form has `id="login-username"`, `id="login-password"`, AND a submit button. Any single marker is too loose — the navbar login-form logout link is in every page.

---

## 5. Endpoints inventory (confirmed)

| Purpose | URL | Auth |
|---------|-----|------|
| Login form | `/login.htm` | no |
| Dashboard | `/eu/alt/dashboard.htm` | yes |
| Profile | `/eu/stu/studentBasicProfile.htm` | yes |
| Student details | `/eu/stu/studentDetailsView.htm` | yes |
| Exam defs | `/eu/exm/viewStudentExamDefinition.htm` | yes |
| Pending results | `/eu/res/pendingResults.htm` | yes |
| Logout | `/eu/alt/logout.htm` | yes |

---

## 6. Page anatomy (HTML patterns)

Three repeating patterns, all Bootstrap 3:

**6.1 Spinner overlay** — `<div id="loader">` + `<div id="spinner">` at top of `<body>`, hidden by a small inline `<script>` once `document.readyState == "complete"`. **Visual effect only** — full content is in the HTTP response. No retry needed.

**6.2 Navbar with welcome** — `<span class="tooltiptext">Welcome NAME</span>` is the most reliable auth marker.

**6.3 Profile key-value blocks** — `<ul class="list-group">` with `<li class="list-group-item">` containing `<span class="view-badge">LABEL</span>` and the value as text. e.g. `Gender = Male`.

**6.4 Tables** — Standard `<table>` with `<th>` headers and `<td>` rows. Used by the exam definitions results.

**6.5 Empty states** — `<div class="alert alert-info">No exam definition for selected academic year.</div>` — surface as info messages, not parse errors.

**6.6 Form dropdowns** — `<select name="academicYear">` with `<option value="N">YEAR-RANGE</option>`. Auto-submits on change via jQuery. Parser exposes `form_options: Dict[name, List[{value, label, selected}]]`.

**6.7 Sidebar nav** — `<a href="/eu/foo/bar.htm">` inside `<aside>` or `<nav>`. Parser extracts `SidebarLink(url, text, is_current)` per page so the TUI can show them as in-page shortcuts.

---

## 7. Rate limiting

Token bucket: 1 request / second, burst 3. Reason: AWS ALB will throttle or block on aggressive crawling; even a polite personal tool should respect the origin.

---

## 8. Session-expiry detection (v0.1 bug)

The v0.1 check `if "name=\"loginform\"" in html` was too loose — the navbar’s logout form has that attribute on every authenticated page, causing constant false "session expired" reports.

**Fix:** require at least 2 of `id="login-username"`, `id="login-password"`, `id="btn-login"`. These only appear on the actual login form.

---

## 9. Spinner真相 (Spinner Truth)

The spinner is a **visual jQuery effect, not a placeholder**. The full page body is in the HTTP response — no second request needed. v0.2 wrongly assumed otherwise and added a retry; v0.3 removed the retry.

---

## 10. TUI architecture (v0.4)

**Layout:** `rich.layout.Layout` with 4 panes — header (fixed top), sidenav (left, fixed width), content (right, fills), statusbar (fixed bottom).

**Header:** `● Online/Offline` dot, `app.ktu.edu.in`, `Welcome NAME` (or "— login required" if offline).

**Sidenav:** Main menu (Dashboard, Exams, Profile, Results, Student Details, Settings, Quit) with keyboard shortcut `1`-`7`. Active item shown with a `▶` marker and reverse-highlighted label. A secondary "Page links" section appears when the current page has sub-links (e.g. dashboard→Payment Request, Blog, etc.).

**Content:** The rendered `PageSnapshot` — welcome line, panel section titles, key-value blocks (profile), tables (exam defs), empty-state alerts, form dropdown options.

**Statusbar:** Last action message, shortcut hints, version.

**Input:** Number for menu (1-7), `B` back, `L` re-login, `F5`/`R` refresh, `Q` quit. No need for arrow keys — kept input dependency-free.

---

## 11. Module map

```
ktu_client.py
├── KTUClient
│   ├── login(username, password)        # CSRF + POST + verify
│   ├── fetch(url, method, data)         # generic GET/POST
│   ├── fetch_exam_notifications(...)     # form POST shortcut
│   ├── logout()
│   └── welcome_name (property)           # parsed from cached page

ktu_parser.py
├── PageSnapshot (dataclass)
│   ├── welcome_user, alerts, panel_titles
│   ├── list_items, kv_blocks, tables
│   ├── empty_messages, form_options
│   └── sidebar_links
├── KTUParser
│   ├── parse(html) -> PageSnapshot
│   ├── is_login_page(html) -> bool
│   ├── extract_welcome / extract_logout_url
│   └── find_sidebar_links(soup) -> [SidebarLink]

ktu_tui.py
├── build_header(client) -> Panel
├── build_sidenav(client, sub_links, current_url) -> Panel
├── render_snapshot(snap, page_url) -> Panel
├── build_statusbar(client, msg) -> Panel
├── build_layout(...) -> Layout
├── fetch_and_render(client, url) -> (Layout, msg, sub_links)
├── run_tui(client)
├── login_screen(client) -> bool
└── cmd_probe, cmd_check_pages
```

---

## 12. Security & ethics

* Credentials are read interactively via `getpass`, held in memory only, never logged or written to disk.
* All requests go through the rate limiter (1 req/s) — no aggressive scraping.
* No CSRF is forged — we read the token from the server, send it back exactly as the browser would.
* No third-party data is sent anywhere — all HTTP traffic is between your machine and `app.ktu.edu.in`.

This tool is intended for accessing **your own student data**. Do not point it at other people’s accounts.

---

## 13. Running

```bash
pip install -r requirements.txt
cd src
python3 ktu_tui.py             # interactive TUI
python3 ktu_tui.py --version
python3 ktu_tui.py --probe     # show public endpoint inventory
python3 ktu_tui.py --check-pages   # test parser against saved HTML
```

---

## 14. Limitations & next steps

* The dashboard’s body values are JS-populated at runtime (the HTML only has panel headers). The TUI shows the section titles and tells the user to visit the page in a browser for live values.
* The sidenav `Page links` is empty for pages whose sidebar is JS-rendered. A future improvement could scrape the JS to find the underlying endpoints.
* Exam dropdown values for the `academicYear` field need to match what the portal serves — the TUI shows the parsed `form_options` so the user can pick from the actual list, but the current default is the empty selection (which the portal interprets as "all").

A natural next step is a `--watch` mode that polls `/eu/exm/viewStudentExamDefinition.htm` every N minutes and prints alerts when new exam definitions appear, enabling a terminal-side notifier.
