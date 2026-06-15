"""
KTU Portal TUI — v0.5  (Textual)

Textual-based terminal UI for the KTU e-Governance portal (app.ktu.edu.in).

Usage:
    python ktu_tui.py                # interactive TUI
    python ktu_tui.py --version      # version
    python ktu_tui.py --check-pages  # test parser against saved HTML
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import List

import requests

from rich.console import Console
from rich.console import Group as RichGroup
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static

from ktu_client import (
    KTUClient,
    DASHBOARD_URL, EXAM_URL, PROFILE_URL,
    STUDENT_DETAILS_URL, PENDING_RESULTS_URL,
    SEMESTER_GRADE_CARD_URL,
)
from ktu_parser import KTUParser, PageSnapshot, SidebarLink

VERSION = "0.5.0"
console = Console()

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
    {"key": "0", "label": "Quit",       "url": None,
     "blurb": "Exit the client"},
]

CLIENT = KTUClient()

# ═══════════════════════════════════════════════════════════════════
# Rich render helpers (unchanged from v0.4)
# ═══════════════════════════════════════════════════════════════════

def _abs_url(url: str) -> str:
    return url if url.startswith("http") else f"https://app.ktu.edu.in{url}"

def _short_url(url: str) -> str:
    for name, val in [("dashboard", DASHBOARD_URL), ("exam", EXAM_URL),
                      ("profile", PROFILE_URL), ("student", STUDENT_DETAILS_URL),
                      ("pending", PENDING_RESULTS_URL)]:
        if val in url:
            return name
    return url.rstrip("/").rsplit("/", 1)[-1] or url

def _spacer() -> Text:
    return Text("")

def _is_portal_widget(tb) -> bool:
    rows_lower = [" ".join(r).lower() for r in tb.rows]
    return "anti ragging" in " ".join(rows_lower) or "feedback form" in " ".join(rows_lower)

def _render_table_block(tb, title: str) -> Table:
    table = Table(title=("[bold]" + title + "[/bold]") if title else None,
                  show_header=True, header_style="bold", border_style="bright_blue",
                  title_justify="left", box=None)
    for h in tb.headers:
        table.add_column(h[:24], overflow="fold")
    for row in tb.rows:
        table.add_row(*(c if c else "\u2014" for c in row))
    return table

def _group_kv(block):
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
                    groups[("identity", "contact", "academic")[
                        (gnames is rule[1]) + 2 * (gnames is rule[2])]].append(row)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            groups["other"].append(row)
    return {g: rows for g, rows in groups.items() if rows}

def _kv_table(block, subtitle):
    table = Table(title=("[bold]" + subtitle + "[/bold]") if subtitle else None,
                  show_header=True, header_style="bold", border_style="bright_blue",
                  title_justify="left")
    table.add_column("Field", style="bold cyan", width=24)
    table.add_column("Value", overflow="fold")
    for row in block:
        table.add_row(row.key, row.value or "\u2014")
    return table

def _render_kv_grouped(block, title):
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

def render_snapshot(snap: PageSnapshot, page_url: str) -> Panel:
    from rich.markup import escape
    if not snap.has_anything:
        return Panel(Text("No extractable data \u2014 the page may need JavaScript.",
                          style="italic yellow"), title="(empty)", border_style="yellow")
    renderables: List = []
    header_parts: List[str] = []
    if snap.welcome_user:
        header_parts.append(f"Welcome, [bold cyan]{escape(snap.welcome_user)}[/bold cyan]")
    if snap.title and snap.title != "APJ Abdul Kalam Technological University":
        header_parts.append(f"[dim]{escape(snap.title)}[/dim]")
    if header_parts:
        renderables.append(Text.from_markup("  " + "  \u2022  ".join(header_parts)))
    _portal_noise = ("password generation", "please wait", "loading")
    filtered_msgs = [m for m in snap.empty_messages
                     if not any(n in m.lower() for n in _portal_noise)]
    tags = {"[!] ": ("error", "red"), "[i] ": ("info", "bright_blue"),
            "[w] ": ("warning", "yellow"), "[OK] ": ("ok", "green")}
    if filtered_msgs:
        renderables.append(_spacer())
    for msg in filtered_msgs:
        matched = False
        for prefix, (t, color) in tags.items():
            if prefix in msg:
                renderables.append(Panel(msg.replace(prefix, ""),
                                         border_style=color, title=t, padding=(0, 1)))
                matched = True
                break
        if not matched:
            renderables.append(Panel(msg, border_style="white", padding=(0, 1)))
    if snap.panel_titles:
        renderables.append(_spacer())
        if DASHBOARD_URL in page_url and len(snap.panel_titles) > 2:
            renderables.append(Text("  Dashboard sections", style="bold underline"))
    for block in snap.kv_blocks:
        renderables.append(_spacer())
        renderables.append(_render_kv_grouped(block, ""))
    for tb in snap.tables:
        if _is_portal_widget(tb):
            continue
        renderables.append(_spacer())
        ttl = tb.headers[0] if tb.headers and len(tb.headers) == 2 else ""
        renderables.append(_render_table_block(tb, ttl))
    if snap.list_items:
        renderables.append(_spacer())
        rendered = Text()
        for li in snap.list_items:
            text = li.description if li.description else li.title
            words = text.split()
            if len(words) <= 1:
                continue
            rendered.append(f"  \u2022 {text}\n")
        if rendered.plain.strip():
            renderables.append(rendered)
    return Panel(RichGroup(*renderables) if renderables else Text(""),
                 title=f"[bold]{escape(_short_url(page_url))}[/bold]",
                 border_style="bright_blue", padding=(0, 1))

def _load_env(path: str = ".env") -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, _, v = line.partition(":")
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

# ═══════════════════════════════════════════════════════════════════
# Screens
# ═══════════════════════════════════════════════════════════════════

class FilterScreen(ModalScreen[str | None]):
    """Pick one option from a list (year / exam type)."""
    def __init__(self, options: list, title: str) -> None:
        self.pick_options = options
        self.pick_title = title
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Label(f"[bold]{self.pick_title}[/bold]  (\u2191\u2193 Enter Esc)",
                    id="filter-title")
        items = [ListItem(Label(o.get("label", f"(option {i+1})")))
                 for i, o in enumerate(self.pick_options)]
        yield ListView(*items, id="filter-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is not None:
            list_view = self.query_one("#filter-list", ListView)
            for i, child in enumerate(list_view.children):
                if child is event.item and i < len(self.pick_options):
                    self.dismiss(self.pick_options[i]["value"])
                    return

    def key_escape(self) -> None:
        self.dismiss(None)

    def key_q(self) -> None:
        self.dismiss(None)


class LoginScreen(Screen[bool]):
    """Login screen."""

    BINDINGS = [
        Binding("escape", "app.quit", "Quit"),
        Binding("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="login-form"):
            yield Static("", id="login-msg")
            yield Label("Username:", classes="login-label")
            yield Input(placeholder="username", id="username")
            yield Label("Password:", classes="login-label")
            yield Input(placeholder="password", password=True, id="password")
            yield Button("  Login  ", variant="primary", id="login-btn")

    def on_mount(self) -> None:
        env = _load_env()
        if "USERNAME" in env:
            self.query_one("#username", Input).value = env["USERNAME"]
        if "PASSWORD" in env:
            self.query_one("#password", Input).value = env["PASSWORD"]
        if env.get("USERNAME") and env.get("PASSWORD"):
            self.set_timer(0.05, lambda: asyncio.create_task(self._do_login()))
        elif env.get("USERNAME"):
            self.query_one("#password", Input).focus()
        else:
            self.query_one("#username", Input).focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login-btn":
            await self._do_login()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._do_login()

    async def _do_login(self) -> None:
        username = self.query_one("#username", Input).value.strip()
        password = self.query_one("#password", Input).value
        if not username or not password:
            self.query_one("#login-msg", Static).update(
                "[red]Username and password required[/red]")
            return
        self.query_one("#login-btn", Button).disabled = True
        self.query_one("#login-msg", Static).update("[cyan]Logging in...[/cyan]")
        try:
            result = await asyncio.to_thread(CLIENT.login, username, password)
            if result.ok:
                self.dismiss(True)
            else:
                self.query_one("#login-btn", Button).disabled = False
                self.query_one("#login-msg", Static).update(
                    f"[red]{result.error or 'Login failed'}[/red]")
        except Exception as e:
            self.query_one("#login-btn", Button).disabled = False
            self.query_one("#login-msg", Static).update(f"[red]Error: {e}[/red]")

    CSS = """
    Screen { align: center middle; }
    #login-form { width: 34; }
    #login-msg { height: 1; margin-bottom: 1; text-align: center; }
    .login-label { margin-top: 1; }
    Input { width: 100%; }
    #login-btn { margin-top: 2; width: 16; }
    """


class PageScreen(Screen):
    """Main TUI screen: sidebar + content area."""

    BINDINGS = [
        Binding("1", "page('1')", "Dashboard"),
        Binding("2", "page('2')", "Exams"),
        Binding("3", "page('3')", "Profile"),
        Binding("4", "page('4')", "Results"),
        Binding("5", "page('5')", "Student Details"),
        Binding("6", "page('6')", "Settings"),
        Binding("q", "app.quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("l", "logout", "Logout"),
        Binding("b", "back", "Back"),
        Binding("up", "sidebar_up", "", show=False),
        Binding("down", "sidebar_down", "", show=False),
        Binding("enter", "sidebar_go", "", show=False),
        Binding("escape", "sidebar_clear", "", show=False),
    ]

    current_url: str = ""
    content_panel: Panel = Panel("")
    _sub_links: list = []
    _sb_idx: int = -1

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield VerticalScroll(id="sidebar")
            yield VerticalScroll(id="content")
        yield Footer()

    def on_mount(self) -> None:
        self.action_page("1")

    # ── sidebar ──────────────────────────────────────────────────

    def _rebuild_sidebar(self) -> None:
        sb = self.query_one("#sidebar", VerticalScroll)
        sb.remove_children()
        if self._sub_links:
            sb.mount(Static(" \u2500\u2500 page links \u2500\u2500",
                            classes="section-header"))
            for i, link in enumerate(self._sub_links, 1):
                display = link.text[:24] + ("\u2026" if len(link.text) > 24 else "")
                m = "\u25b8" if (i - 1) == self._sb_idx else " "
                cls = "sub-link" + (" selected" if (i - 1) == self._sb_idx else "")
                sb.mount(Static(f" {m}{i}  {display}", classes=cls))
            sb.mount(Static("", classes="spacer"))
        sb.mount(Static(" [b]ack  [r]efresh  [l]ogin  [q]uit", classes="hint"))

    def action_sidebar_up(self) -> None:
        if not self._sub_links:
            return
        self._sb_idx = ((self._sb_idx - 1) if self._sb_idx >= 0
                        else len(self._sub_links) - 1)
        self._rebuild_sidebar()

    def action_sidebar_down(self) -> None:
        if not self._sub_links:
            return
        self._sb_idx = ((self._sb_idx + 1) if self._sb_idx >= 0 else 0)
        self._rebuild_sidebar()

    def action_sidebar_go(self) -> None:
        if 0 <= self._sb_idx < len(self._sub_links):
            self._follow_sub(self._sub_links[self._sb_idx])

    def action_sidebar_clear(self) -> None:
        self._sb_idx = -1
        self._rebuild_sidebar()

    # ── page loading ─────────────────────────────────────────────

    def _follow_sub(self, target: SidebarLink) -> None:
        url = _abs_url(target.url)
        self._do_fetch(url, f"\u2192 {target.text}")

    def _do_fetch(self, url: str, status: str = "") -> None:
        if not CLIENT.logged_in:
            return
        self.current_url = url
        resp = CLIENT.fetch(url)
        if not resp.ok:
            self._show_error(resp.error or "Fetch failed")
            return
        snap = KTUParser.parse(resp.html)
        self._sub_links = [sl for sl in snap.sidebar_links
                           if sl.text and sl.text.lower() != "logout"]
        self._sb_idx = -1

        # Auto-detect form options and launch filter if needed
        semester_raw = snap.form_options.get("semesterId", [])
        raw_year = snap.form_options.get("academicYear", [])
        raw_type = snap.form_options.get("examType", [])
        semester_opts = [o for o in semester_raw if o.get("value")]
        year_opts = [o for o in raw_year if o.get("value")]
        type_opts = [o for o in raw_type if o.get("value")]

        if semester_opts:
            asyncio.create_task(
                self._start_filter_flow("semester", semester_opts, url))
            return
        if year_opts or type_opts:
            asyncio.create_task(
                self._start_filter_flow("exam", year_opts, type_opts, url))
            return

        content = render_snapshot(snap, url)
        self._show_content(content)

    async def _start_filter_flow(self, kind: str, *args, url: str) -> None:
        if kind == "semester":
            opts = args[0]
            result = await self.app.push_screen_wait(
                FilterScreen(opts, "Semester"))
            if result is None:
                return
            resp = await asyncio.to_thread(
                CLIENT.fetch_semester_grade_card, result)
        elif kind == "exam":
            year_opts, type_opts = args
            year = ""
            etype = ""
            if year_opts:
                result = await self.app.push_screen_wait(
                    FilterScreen(year_opts, "Academic Year"))
                if result is None:
                    return
                year = result
            if type_opts:
                result = await self.app.push_screen_wait(
                    FilterScreen(type_opts, "Exam Type"))
                if result is None:
                    return
                etype = result
            resp = await asyncio.to_thread(
                CLIENT.fetch_exam_notifications, year, etype)
        else:
            return

        if not resp.ok:
            self._show_error(resp.error or "Filter failed")
            return
        snap = KTUParser.parse(resp.html)
        self._sub_links = [sl for sl in snap.sidebar_links
                           if sl.text and sl.text.lower() != "logout"]
        self._sb_idx = -1
        content = render_snapshot(snap, url)
        self._show_content(content)

    def _show_content(self, panel: Panel) -> None:
        self.content_panel = panel
        cnt = self.query_one("#content", VerticalScroll)
        cnt.remove_children()
        cnt.mount(Static(panel))
        self._rebuild_sidebar()

    def _show_error(self, msg: str) -> None:
        cnt = self.query_one("#content", VerticalScroll)
        cnt.remove_children()
        self._sub_links = []
        self._rebuild_sidebar()
        cnt.mount(Static(Panel(f"[red]{msg}[/red]", border_style="red")))

    # ── actions ──────────────────────────────────────────────────

    def action_page(self, key: str) -> None:
        item = next((i for i in MAIN_MENU if i["key"] == key), None)
        if item is None:
            return
        url = item["url"]
        if url is None:
            if key == "6":
                self._show_error("Settings (placeholder)")
            return
        self._sub_links = []
        self._sb_idx = -1
        self._do_fetch(url)

    def action_refresh(self) -> None:
        if self.current_url:
            self._do_fetch(self.current_url)

    def action_back(self) -> None:
        self.action_page("1")

    def action_logout(self) -> None:
        CLIENT.logout()
        self.app.pop_screen()
        self.app.push_screen(LoginScreen(), self.app._after_login)


# ═══════════════════════════════════════════════════════════════════
# App
# ═══════════════════════════════════════════════════════════════════

class KTUApp(App):
    TITLE = "KTU Portal"
    SUB_TITLE = f"v{VERSION}"

    CSS = """
    Screen { background: $surface; }
    #sidebar { width: 28; border-right: solid $primary; padding: 0 1; }
    #content { width: 1fr; padding: 0 1; }
    .sub-link { padding: 0 1; height: 1; }
    .sub-link:hover { background: $primary 30%; }
    .sub-link.selected { background: $primary 20%; text-style: bold; }
    .section-header { padding: 0 1; color: $text-disabled; text-style: italic; }
    .hint { padding: 0 1; color: $text-disabled; }
    .spacer { height: 1; }
    """

    def on_mount(self) -> None:
        self.push_screen(LoginScreen(), self._after_login)

    def _after_login(self, ok: bool) -> None:
        if not ok:
            self.exit(1)
        self.push_screen(PageScreen())


# ═══════════════════════════════════════════════════════════════════
# Non-interactive commands
# ═══════════════════════════════════════════════════════════════════

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
        console.print(f"  form_options:   {list(snap.form_options.keys())}")
        console.print(f"  kv_blocks:      {len(snap.kv_blocks)}")
        console.print(f"  tables:         {len(snap.tables)}")
        console.print(f"  sidebar_links:  {len(snap.sidebar_links)}")
        for sl in snap.sidebar_links[:5]:
            console.print(f"      {sl.text!r}  \u2192  {sl.url}")
    return 0


def cmd_probe() -> int:
    """Check public endpoint accessibility (no auth)."""
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
            if r.status_code == 302 and r.headers.get("Location", "").endswith("/login.htm"):
                status = "302 -> /login.htm (auth required)"
            elif r.status_code == 200:
                status = "200 OK"
            else:
                status = f"{r.status_code}"
        except requests.RequestException as e:
            status = f"error: {e}"
        table.add_row(name, url, status)
    console.print(table)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="KTU Portal TUI client v" + VERSION)
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument("--probe", action="store_true", help="show public endpoint inventory")
    parser.add_argument("--check-pages", action="store_true",
                        help="test the parser against saved HTML pages in debug/pages/")
    args = parser.parse_args()
    if args.version:
        print(f"ktu_tui v{VERSION}")
        return 0
    if args.probe:
        return cmd_probe()
    if args.check_pages:
        return cmd_check_pages()
    app = KTUApp()
    app.run()


if __name__ == "__main__":
    sys.exit(main())
