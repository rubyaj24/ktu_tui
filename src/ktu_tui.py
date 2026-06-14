"""
KTU Portal TUI — v0.4

Major rewrite: header / sidenav / content / statusbar layout.

UI references (from uploaded mockups):
  * Top fixed header with app title + connection status
  * Left vertical sidenav with main menu (Dashboard, Exams, Results,
    Fees, Monitor, Settings)
  * Content panel on the right; on each page, a sub-sidenav is shown
    with the page's own sub-links (Payment Request, Blog, etc.)
  * Bottom statusbar with shortcut hints
  * Keypress navigation: enter a number + Enter to select; or "b" to
    go back, "q" to quit, "r" to refresh, "l" to (re)login

Main scope: profile, exam notifications, results — the other items in
the sidenav are placeholders (exposed so you can click them, but they
fall through to "fetch this page" if you really need to).

Usage:
    python ktu_tui.py                # interactive TUI
    python ktu_tui.py --probe        # public endpoint inventory
    python ktu_tui.py --version      # version
    python ktu_tui.py --check-pages  # test parser against saved pages
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import List, Optional

import requests
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from ktu_client import (
    KTUClient,
    DASHBOARD_URL,
    EXAM_URL,
    PROFILE_URL,
    STUDENT_DETAILS_URL,
    PENDING_RESULTS_URL,
)
from ktu_parser import KTUParser, PageSnapshot, SidebarLink, KVRow

VERSION = "0.4.0"

console = Console()


# ---------------------------------------------------------------------------
# Main-menu items (always visible in the left sidenav)
# ---------------------------------------------------------------------------
#
# These are the "main" features per your spec.  The other sidenav items
# from the mockup (Dashboard, Fees, Monitor, Settings) are exposed too —
# but they fall through to a generic page fetch rather than being full
# features, so the focus stays on the data we actually came for.

MAIN_MENU: List[dict] = [
    {"key": "1", "label": "Dashboard",  "url": DASHBOARD_URL,
     "blurb": "Welcome, Fee Details, Suraksha, Alerts"},
    {"key": "2", "label": "Exams",      "url": EXAM_URL,
     "blurb": "Exam definitions + search by year / type"},
    {"key": "3", "label": "Profile",    "url": PROFILE_URL,
     "blurb": "Basic profile (gender, DOB, category, blood group, ...)"},
    {"key": "4", "label": "Results",    "url": PENDING_RESULTS_URL,
     "blurb": "Pending results (year / sem / branch)"},
    {"key": "5", "label": "Student Details", "url": STUDENT_DETAILS_URL,
     "blurb": "Extended details (address, guardian, bank, ...)"},
    {"key": "6", "label": "Settings",   "url": None,
     "blurb": "Preferences, theme, rate limit"},
    # below are utility items, not real portal pages
    {"key": "0", "label": "Quit",       "url": None,
     "blurb": "Exit the client"},
]


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def build_header(client: KTUClient) -> Panel:
    """Compact header: connection status + welcome."""
    who = client.welcome_name or client.username or ""
    if client.logged_in:
        status = Text("●", style="bold green")
        status.append(" Online  ", style="green")
        status.append("app.ktu.edu.in", style="dim")
    else:
        status = Text("●", style="bold red")
        status.append(" Offline", style="red")
        status.append("  — not logged in", style="dim")

    left = Text("  ")
    left.append_text(status)

    right = Text(f"Welcome {who}", style="cyan") if who else Text("")

    from rich.table import Table
    row = Table.grid(expand=True)
    row.add_column(justify="left", ratio=1)
    row.add_column(justify="right")
    row.add_row(left, right)

    return Panel(row, title="KTU Portal", title_align="left",
                 border_style="bright_blue", height=3, padding=(0, 1))


# ---------------------------------------------------------------------------
# Sidenav (main menu + per-page sub-links)
# ---------------------------------------------------------------------------

def build_sidenav(client: KTUClient, sub_links: List[SidebarLink],
                  current_url: Optional[str],
                  selected_sub: int = -1) -> Panel:
    """Left sidenav: main menu + per-page sub-links."""
    lines: List = [Text("")]

    for item in MAIN_MENU:
        is_current = (current_url and item.get("url") == current_url)
        marker = "▸" if is_current else " "
        key = Text(f"{marker}{item['key']}", style="bold cyan")
        label = item["label"]
        style = "reverse bold" if is_current else ""
        lines.append(Text.assemble(" ", key, "  ", Text(label, style=style)))

    if sub_links:
        lines.append(Text(""))
        lines.append(Text(" ── links ──", style="dim italic"))
        for i, link in enumerate(sub_links, 1):
            display = link.text[:22] + ("…" if len(link.text) > 22 else "")
            is_sel = (i - 1) == selected_sub
            m = "▸" if is_sel else " "
            idx = Text(f"{m}{i}", style="bold cyan" if is_sel else "dim")
            txt = Text(f" {display}", style="reverse bold" if is_sel else "dim")
            lines.append(Text.assemble(" ", idx, txt))

    from rich.console import Group
    return Panel(Group(*lines), title="Menu", border_style="bright_blue",
                 title_align="left", padding=(0, 1))


# ---------------------------------------------------------------------------
# Content renderer (PageSnapshot → rich renderables)
# ---------------------------------------------------------------------------

def render_snapshot(snap: PageSnapshot, page_url: str) -> Panel:
    """Render a PageSnapshot into a single Panel."""
    if not snap.has_anything:
        return Panel(Text("No extractable data — the page may need JavaScript.",
                          style="italic yellow"),
                     title="(empty)", border_style="yellow")

    renderables: List = []
    from rich.markup import escape

    # 1. Welcome / page header
    header_parts: List[str] = []
    if snap.welcome_user:
        header_parts.append(f"Welcome, [bold cyan]{escape(snap.welcome_user)}[/bold cyan]")
    if snap.title and snap.title != "APJ Abdul Kalam Technological University":
        header_parts.append(f"[dim]{escape(snap.title)}[/dim]")
    if header_parts:
        renderables.append(Text.from_markup("  " + "  •  ".join(header_parts)))

    # 2. Alert / status messages (compact single-line)
    for msg in snap.empty_messages:
        tags = {"[!] ": ("error", "red"), "[i] ": ("info", "bright_blue"),
                "[w] ": ("warning", "yellow"), "[OK] ": ("ok", "green")}
        matched = False
        for prefix, (title, color) in tags.items():
            if prefix in msg:
                renderables.append(Panel(msg.replace(prefix, ""),
                                         border_style=color, title=title,
                                         padding=(0, 1)))
                matched = True
                break
        if not matched:
            renderables.append(Panel(msg, border_style="white", padding=(0, 1)))

    # 3. Panel section titles
    if snap.panel_titles:
        is_dashboard = DASHBOARD_URL in page_url
        if is_dashboard and len(snap.panel_titles) > 2:
            renderables.append(Text("  Dashboard sections", style="bold underline"))
            for t in snap.panel_titles:
                renderables.append(Text(f"    • {t}", style="cyan"))
            renderables.append(Text("  (JS-populated — visit in a browser for live values)",
                                    style="dim italic"))
        else:
            for t in snap.panel_titles:
                renderables.append(Text(f"  {t}", style="bold"))

    # 4. KV blocks (profile)
    if snap.kv_blocks:
        merged = []
        for block in snap.kv_blocks:
            merged.extend(block)
        renderables.append(_render_kv_grouped(merged, ""))

    # 5. Tables
    for tb in snap.tables:
        renderables.append(_render_table_block(tb, ""))

    # 6. List items (alerts)
    if snap.list_items:
        lt = Table(show_header=True, header_style="bold", border_style="bright_blue")
        lt.add_column("#", width=3, style="dim")
        lt.add_column("Title", style="bold")
        lt.add_column("Details", overflow="fold")
        for j, li in enumerate(snap.list_items, 1):
            lt.add_row(str(j), li.title, li.description)
        renderables.append(lt)

    # 7. Form options (exam year / type pickers)
    if snap.form_options:
        for form_name, opts in snap.form_options.items():
            nice = form_name[0].upper() + form_name[1:] if form_name else ""
            renderables.append(Text(f"  {nice}", style="bold underline"))
            for opt in opts:
                val = opt['value']
                label = opt['label']
                if not label or label in ("-Select-", "Select"):
                    continue
                sel = " ◀ selected" if opt.get("selected") else ""
                renderables.append(Text.from_markup(
                    f"    {label}  [dim]({val}{sel})[/dim]" if val
                    else f"    {label}"))

    from rich.console import Group
    return Panel(
        Group(*renderables),
        title=f"[bold]{_short_url(page_url)}[/bold]",
        border_style="bright_blue", title_align="left", padding=(0, 1),
    )


def _short_url(url: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url)
    return f"{p.netloc}{p.path}"


def _render_kv_table(block: List[KVRow], title: str) -> Table:
    table = Table(title=f"[bold]{title}[/bold]", show_header=True,
                  header_style="bold", border_style="blue")
    table.add_column("Field", style="bold cyan", width=28)
    table.add_column("Value", overflow="fold")
    for row in block:
        table.add_row(row.key, row.value if row.value else Text("—", style="dim"))
    return table


def _render_table_block(tb, title: str) -> Table:
    table = Table(title=f"[bold]{title}[/bold]" if title else None,
                  show_header=True, header_style="bold", border_style="bright_blue")
    if tb.headers:
        for h in tb.headers:
            table.add_column(h, overflow="fold")
    else:
        ncols = max((len(r) for r in tb.rows), default=1)
        for i in range(ncols):
            table.add_column(f"Col {i+1}", overflow="fold")
    for row in tb.rows:
        padded = row + [""] * (len(table.columns) - len(row))
        table.add_row(*padded)
    return table


# ---------------------------------------------------------------------------
# Statusbar
# ---------------------------------------------------------------------------

def build_statusbar(client: KTUClient, last_msg: str = "") -> Panel:
    """Bottom statusbar: last status + shortcut hints."""
    left = Text()
    if last_msg:
        left.append(" " + last_msg + "  ", style="italic")
    else:
        left.append(" Ready. ", style="italic dim")
    left.append("│", style="dim")
    left.append(" R", style="bold cyan"); left.append("refresh", style="dim")
    left.append(" │", style="dim")
    left.append(" L", style="bold cyan"); left.append("login", style="dim")
    left.append(" │", style="dim")
    left.append(" B", style="bold cyan"); left.append("back", style="dim")
    left.append(" │", style="dim")
    left.append(" Q", style="bold cyan"); left.append("quit", style="dim")

    right = Text(f" v{VERSION}", style="dim")
    body = Table.grid(expand=True)
    body.add_column(justify="left", ratio=1)
    body.add_column(justify="right")
    body.add_row(left, right)

    return Panel(body, height=3, border_style="bright_blue", padding=(0, 1))


# ---------------------------------------------------------------------------
# Layout helper
# ---------------------------------------------------------------------------

def build_layout(client: KTUClient, sub_links: List[SidebarLink],
                 content_panel: Panel, current_url: Optional[str],
                 last_msg: str = "", selected_sub: int = -1) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="status", size=3),
    )
    layout["body"].split_row(
        Layout(name="sidenav", ratio=1),
        Layout(name="content", ratio=3),
    )
    layout["header"].update(build_header(client))
    layout["sidenav"].update(build_sidenav(client, sub_links, current_url, selected_sub))
    layout["content"].update(content_panel)
    layout["status"].update(build_statusbar(client, last_msg))
    return layout


# ---------------------------------------------------------------------------
# Page flow
# ---------------------------------------------------------------------------

def fetch_and_render(client: KTUClient, url: str, last_msg: str = "") -> tuple[Layout, str, List[SidebarLink]]:
    """Fetch a page, parse it, build a Layout.  Returns (layout, message, sub_links)."""
    if not client.logged_in:
        return (build_layout(
            client, [], Panel("Not logged in. Press L to log in.",
                              border_style="red"), None, last_msg),
            "Not logged in.", [])

    res = client.fetch(url)
    if not res.ok:
        return (build_layout(
            client, [], Panel(f"[red]{res.error}[/red]", border_style="red"),
            url, last_msg),
            f"Error: {res.error}", [])

    snap = KTUParser.parse(res.html)
    sub_links = [sl for sl in snap.sidebar_links
                 if sl.text and sl.text.lower() != "logout"]
    content = render_snapshot(snap, url)
    layout = build_layout(client, sub_links, content, url,
                          last_msg=last_msg or "Loaded.")
    return (layout, f"Loaded {url}", sub_links)


def show_main_menu_arrow(client) -> str:
    """Arrow-key navigable main menu.

    Returns the same strings as *show_main_menu*:
    ``'quit'``, ``'login'``, ``'settings'``, ``'back'``, or a menu key
    like ``'1'``.
    """
    from ktu_input import pick
    items = [(m["key"], m["label"], m.get("blurb", ""))
             for m in MAIN_MENU if m["key"] != "0"]
    console.clear()
    while True:
        picked = pick(items, title="Main Menu")
        if picked is None:
            console.clear()
            return "back"
        if isinstance(picked, str) and picked in ("l", "q", "b"):
            return {"l": "login", "q": "quit", "b": "back"}[picked]
        if isinstance(picked, tuple):
            console.clear()
            return picked[0]
        return "back"
def show_main_menu(client: KTUClient) -> str:
    """Show the main menu (sidenav only, no page loaded).  Returns
    the action the user picked: 'quit', 'login', or a menu key like '1'."""
    # Build an empty content panel with prompt to pick a page
    content = Panel(
        Align.center(Text(
            "\n\n  Select a section from the left to begin.\n"
            "  Press the number key + Enter  (e.g.  1<Enter>)\n"
            "\n"
            "  Or type one of:  L  (re)login  •  B  back  •  Q  quit\n\n",
            style="dim")),
        border_style="blue", title="[bold]Home[/bold]")
    layout = build_layout(client, [], content, None,
                          last_msg="Press 1-6 to pick a page, L to login.")

    with Live(layout, console=console, refresh_per_second=0, screen=False) as live:
        while True:
            choice = Prompt.ask("[bold cyan]Pick[/bold cyan]").strip().lower()
            if choice in ("q", "0", "quit"):
                return "quit"
            if choice in ("l", "login"):
                return "login"
            if choice in ("b", "back"):
                return "back"
            # number key
            for item in MAIN_MENU:
                if item["key"] == choice:
                    if item["url"] is None:
                        if item["label"] == "Quit":
                            return "quit"
                        if item["label"] == "Settings":
                            return "settings"
                    return item["key"]
            # invalid
            console.print(f"[red]Unknown choice:[/red] {choice!r}.  "
                          f"Try 1-6, L, B, or Q.")


def run_tui(client: KTUClient) -> int:
    """Main interactive loop.  Returns process exit code."""
    while True:
        # 1. Login if needed
        if not client.logged_in:
            if not login_screen(client):
                return 0

        # 2. Main menu (arrow-key navigable)
        action = show_main_menu_arrow(client)
        if action == "quit":
            console.print("[bold cyan]Goodbye![/bold cyan]")
            return 0
        if action == "login":
            client.logout()
            continue
        if action == "settings":
            show_settings(client)
            continue
        if action == "back":
            continue

        # 3. Page loop — user picked a section
        if run_page_loop(client, action) == "quit":
            return 0


def _abs_url(url: str) -> str:
    if url.startswith("http"):
        return url
    return f"https://app.ktu.edu.in{url}"


def _follow_sub_link(client: KTUClient, target: SidebarLink) -> tuple[Panel, str, List[SidebarLink], str]:
    """Follow a sub-link and return ``(content_panel, new_url, sub_links, msg)``."""
    new_url = _abs_url(target.url)
    res = client.fetch(new_url)
    if not res.ok:
        return None, "", [], f"Sub-link error: {res.error}"
    snap = KTUParser.parse(res.html)
    new_sub = [sl for sl in snap.sidebar_links
               if sl.text and sl.text.lower() != "logout"]
    content = render_snapshot(snap, new_url)
    return content, new_url, new_sub, f"→ {target.text}"


def run_page_loop(client: KTUClient, menu_key: str) -> str:
    """After the user picks a section from the main menu, this loop
    shows that page, lets them click on a sub-link, refresh, go back,
    re-login, or quit.  Returns ``'quit'`` / ``'back'`` / ``'login'``.

    Arrow keys navigate sub-links; Enter follows the highlighted one;
    single keys (r, b, l, q) act immediately.
    """
    from ktu_input import read_key, KEY_UP, KEY_DOWN, KEY_ENTER, KEY_CTRL_C, KEY_ESC

    item = next(i for i in MAIN_MENU if i["key"] == menu_key)
    url = item["url"]
    last_msg = ""
    sub_idx = -1

    if url is None:
        return "back"

    layout, msg, sub_links = fetch_and_render(client, url)
    content_panel = layout["content"].renderable
    sub_idx = -1

    with Live(layout, console=console, refresh_per_second=0, screen=True) as live:
        while True:
            try:
                k = read_key()
            except (EOFError, KeyboardInterrupt):
                return "quit"

            # ── command keys ──────────────────────────────────────────
            if k in ("q", "0"):
                return "quit"
            if k == "b":
                return "back"
            if k == "l":
                client.logout()
                return "login"
            if k == "r":
                try:
                    if "exam" in url.lower() or "examtype" in (
                        res_html_for_exam_check(client, url) or ""
                    ).lower():
                        academic_year, exam_type = _prompt_exam_filters(client, url)
                        if academic_year is None:
                            continue
                        res = client.fetch_exam_notifications(academic_year, exam_type)
                        if res.ok:
                            snap = KTUParser.parse(res.html)
                            new_content = render_snapshot(snap, url)
                            new_sub = [sl for sl in snap.sidebar_links
                                       if sl.text and sl.text.lower() != "logout"]
                            live.update(build_layout(
                                client, new_sub, new_content, url,
                                last_msg=f"Refreshed: year={academic_year!r}, type={exam_type!r}"))
                            content_panel = new_content
                            sub_links = new_sub
                            sub_idx = -1
                    else:
                        new_layout, new_msg, new_sub = fetch_and_render(
                            client, url, last_msg="Refreshing...")
                        live.update(new_layout)
                        content_panel = new_layout["content"].renderable
                        sub_links = new_sub
                        sub_idx = -1
                        last_msg = new_msg
                except Exception:
                    last_msg = "Refresh failed"
                continue

            # ── arrow keys ────────────────────────────────────────────
            if k == KEY_UP and sub_links:
                sub_idx = (sub_idx - 1) % len(sub_links) if sub_idx >= 0 else len(sub_links) - 1
                live.update(build_layout(client, sub_links, content_panel,
                                          url, last_msg="", selected_sub=sub_idx))
                continue

            if k == KEY_DOWN and sub_links:
                sub_idx = (sub_idx + 1) % len(sub_links) if sub_idx >= 0 else 0
                live.update(build_layout(client, sub_links, content_panel,
                                          url, last_msg="", selected_sub=sub_idx))
                continue

            if k == KEY_ENTER and 0 <= sub_idx < len(sub_links):
                try:
                    cp, new_url, new_sub, msg = _follow_sub_link(client, sub_links[sub_idx])
                    if cp is None:
                        last_msg = msg
                        continue
                    live.update(build_layout(client, new_sub, cp, new_url, last_msg=msg))
                    url, sub_links, content_panel, sub_idx = new_url, new_sub, cp, -1
                except Exception:
                    last_msg = "Link failed"
                continue

            if k == KEY_ESC:
                sub_idx = -1
                live.update(build_layout(client, sub_links, content_panel,
                                          url, last_msg="", selected_sub=-1))
                continue

            # ── numeric keys ──────────────────────────────────────────
            if k and len(k) == 1 and k.isdigit():
                if k in (i["key"] for i in MAIN_MENU):
                    return k
                idx = int(k) - 1
                if 0 <= idx < len(sub_links):
                    try:
                        cp, new_url, new_sub, msg = _follow_sub_link(client, sub_links[idx])
                        if cp is None:
                            last_msg = msg
                            continue
                        live.update(build_layout(client, new_sub, cp, new_url, last_msg=msg))
                        url, sub_links, content_panel, sub_idx = new_url, new_sub, cp, -1
                    except Exception:
                        last_msg = "Link failed"
                continue

            if k == KEY_CTRL_C:
                return "quit"


def res_html_for_exam_check(client: KTUClient, url: str) -> str:
    """Used by the refresh branch to detect whether we're on the exam page
    without making the main flow depend on the cache."""
    if not client.logged_in:
        return ""
    res = client.fetch(url)
    return res.html if res.ok else ""


def _prompt_exam_filters(client: KTUClient, url: str) -> tuple[Optional[str], str]:
    """Show the academicYear / examType pickers based on the page's
    real dropdown options.  Returns (year, type) or (None, '') if cancelled."""
    res = client.fetch(url)
    if not res.ok:
        return (None, "")
    snap = KTUParser.parse(res.html)
    year_opts = snap.form_options.get("academicYear", [])
    type_opts = snap.form_options.get("examType", [])
    if not year_opts:
        # fall back to free-text
        year = Prompt.ask("Academic Year", default="").strip()
        if not year:
            return (None, "")
        etype = Prompt.ask("Exam Type (blank=all)", default="").strip()
        return (year, etype)
    # pick from dropdown
    console.print("\n[bold]Academic Year:[/bold]")
    for i, o in enumerate(year_opts, 1):
        sel = " (default)" if o.get("selected") else ""
        console.print(f"  {i:>2}. value=[cyan]{o['value']!r}[/cyan]  "
                      f"label={o['label']!r}{sel}")
    year_idx = Prompt.ask("Pick", default="1").strip()
    if not year_idx.isdigit() or not (1 <= int(year_idx) <= len(year_opts)):
        console.print("[red]invalid[/red]")
        return (None, "")
    year = year_opts[int(year_idx) - 1]["value"]

    console.print("\n[bold]Exam Type:[/bold]")
    for i, o in enumerate(type_opts, 1):
        sel = " (default)" if o.get("selected") else ""
        console.print(f"  {i:>2}. value=[cyan]{o['value']!r}[/cyan]  "
                      f"label={o['label']!r}{sel}")
    if type_opts:
        type_idx = Prompt.ask("Pick (blank=all)", default="").strip()
        if type_idx.isdigit() and 1 <= int(type_idx) <= len(type_opts):
            etype = type_opts[int(type_idx) - 1]["value"]
        else:
            etype = ""
    else:
        etype = ""
    return (year, etype)


# ---------------------------------------------------------------------------
# Login + settings
# ---------------------------------------------------------------------------

def login_screen(client: KTUClient) -> bool:
    """Prompt for credentials, attempt login, show result.  Returns True
    on success."""
    while True:
        console.clear()
        console.print(Panel(
            Align.center(Text("Sign in to app.ktu.edu.in\n"
                              "(credentials stay in memory only)",
                              style="bold cyan")),
            border_style="blue"))
        username = Prompt.ask("[bold]Username[/bold]")
        password = getpass.getpass("Password (input hidden): ")

        with console.status("[cyan]Logging in...[/cyan]"):
            try:
                result = client.login(username, password); ok = result.ok; msg = result.error or "login succeeded"
            except Exception as e:
                ok, msg = False, f"Error: {e}"

        if ok:
            console.print(f"[bold green]✓ {msg}[/bold green]")
            return True
        console.print(f"[bold red]✗ {msg}[/bold red]")
        retry = Prompt.ask("Try again?", choices=["y", "n"], default="y")
        if retry != "y":
            return False


def show_settings(client: KTUClient) -> None:
    console.clear()
    console.print(Panel("[bold]Settings[/bold] (placeholder — extend as needed)",
                        border_style="blue"))
    table = Table(show_header=True, header_style="bold", border_style="blue")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("Rate limit (req/sec)", str(client.rate_limit_per_sec))
    table.add_row("Min interval (sec)", f"{client.min_interval_sec:.2f}")
    table.add_row("Base URL", client.BASE_URL)
    table.add_row("Logged in", "yes" if client.logged_in else "no")
    table.add_row("Username", client.username or "—")
    table.add_row("Welcome name", client.welcome_name or "—")
    console.print(table)
    Prompt.ask("\nPress Enter to go back", default="", show_default=False)


# ---------------------------------------------------------------------------
# Non-interactive commands
# ---------------------------------------------------------------------------

def cmd_probe() -> int:
    console.print(Panel("Public endpoints (no auth)", border_style="cyan"))
    table = Table(show_header=True, header_style="bold", border_style="blue")
    table.add_column("Purpose", style="bold")
    table.add_column("URL", overflow="fold")
    table.add_column("Status")

    urls = [
        ("Login page (anon)", "https://app.ktu.edu.in/login.htm"),
        ("Dashboard (auth)", DASHBOARD_URL),
        ("Profile (auth)", PROFILE_URL),
        ("Exam defs (auth)", EXAM_URL),
        ("Student details (auth)", STUDENT_DETAILS_URL),
        ("Pending results (auth)", PENDING_RESULTS_URL),
    ]
    client = KTUClient()
    for name, url in urls:
        try:
            r = client.session.get(url, allow_redirects=False, timeout=10)
            status = f"{r.status_code}"
            if r.status_code == 302 and r.headers.get("Location", "").endswith("/login.htm"):
                status = "302 → /login.htm (auth required ✓)"
            elif r.status_code == 200:
                status = "200 OK"
            else:
                status = f"{r.status_code} {r.reason}"
        except requests.RequestException as e:
            status = f"error: {e}"
        table.add_row(name, url, status)
    console.print(table)
    return 0


def cmd_check_pages() -> int:
    import pathlib
    pages_dir = pathlib.Path(__file__).parent.parent / "debug" / "pages"
    if not pages_dir.exists():
        console.print(f"[red]No pages directory at {pages_dir}[/red]")
        return 1
    for path in sorted(pages_dir.glob("*.html")):
        html = path.read_text()
        snap = KTUParser.parse(html)
        console.rule(f"[bold]{path.name}[/bold]")
        console.print(f"  welcome:        {snap.welcome_user!r}")
        console.print(f"  is_login_page:  {KTUParser.is_login_page(html)}")
        console.print(f"  panel_titles:   {snap.panel_titles}")
        console.print(f"  empty_messages: {snap.empty_messages}")
        console.print(f"  kv_blocks:      {len(snap.kv_blocks)}")
        console.print(f"  tables:         {len(snap.tables)}")
        console.print(f"  form_options:   {list(snap.form_options.keys())}")
        console.print(f"  sidebar_links:  {len(snap.sidebar_links)}")
        for sl in snap.sidebar_links[:5]:
            console.print(f"      {sl.text!r}  →  {sl.url}")
        for block in snap.kv_blocks:
            for row in block:
                console.print(f"    {row.key:<25} = {row.value!r}")
    return 0


# ---------------------------------------------------------------------------
# KV grouping helpers
# ---------------------------------------------------------------------------


def _group_kv(block):
    """Group KV rows by semantic category. Returns dict."""
    groups = {"identity": [], "contact": [], "academic": [], "other": []}
    rule = (
        ("name", "father", "mother", "guardian", "dob", "date of birth",
         "gender", "blood", "aadhar", "religion", "caste", "cast", "nationality",
         "category", "mother tongue", "language", "marital"),
        ("address", "city", "state", "district", "pincode", "pin", "phone",
         "mobile", "email", "contact"),
        ("admission", "roll", "register", "branch", "semester", "sem", "course",
         "college", "university", "academic year", "ktu id"),
    )
    for row in block:
        klow = (row.key or "").lower()
        placed = False
        for gnames in rule:
            for n in gnames:
                if n in klow:
                    if gnames is rule[0]:
                        groups["identity"].append(row); break
                    elif gnames is rule[1]:
                        groups["contact"].append(row); break
                    else:
                        groups["academic"].append(row); break
            else:
                continue
            placed = True
            break
        if not placed:
            groups["other"].append(row)
    return {g: rows for g, rows in groups.items() if rows}


def _render_kv_grouped(block, title):
    from rich.console import Group as RichGroup
    groups = _group_kv(block)
    titles = {"identity": "Personal", "contact": "Contact", "academic": "Academic", "other": "Other"}
    items = []
    if title:
        items.append(Text(title, style="bold underline cyan"))
    if len(groups) == 1:
        gname, rows = next(iter(groups.items()))
        items.append(_kv_table(rows, titles.get(gname, gname)))
        return RichGroup(*items)
    for gname, rows in groups.items():
        items.append(Text(titles.get(gname, gname), style="bold cyan"))
        items.append(_kv_table(rows, ""))
    return RichGroup(*items)


def _kv_table(block, subtitle):
    table = Table(title=("[bold]" + subtitle + "[/bold]") if subtitle else None,
                  show_header=True, header_style="bold", border_style="bright_blue",
                  title_justify="left")
    table.add_column("Field", style="bold cyan", width=24)
    table.add_column("Value", overflow="fold")
    for row in block:
        table.add_row(row.key, row.value or "—")
    return table


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="KTU Portal TUI client v" + VERSION)
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument("--probe", action="store_true", help="show public endpoint inventory")
    parser.add_argument("--check-pages", action="store_true",
                        help="test the parser against the saved HTML pages in debug/pages/")
    args = parser.parse_args()

    if args.version:
        print(f"ktu_tui v{VERSION}")
        return 0
    if args.probe:
        return cmd_probe()
    if args.check_pages:
        return cmd_check_pages()

    client = KTUClient()
    try:
        return run_tui(client)
    except KeyboardInterrupt:
        console.print("\n[bold cyan]Goodbye![/bold cyan]")
        return 0
    finally:
        client.logout()


if __name__ == "__main__":
    sys.exit(main())
