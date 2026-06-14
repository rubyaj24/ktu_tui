"""
Render a few mock screens to confirm the new TUI looks right.
Does NOT make any HTTP requests. Uses saved HTML from debug/pages/.

Run: python preview_screens.py
"""
import pathlib
from rich.console import Console
from rich.panel import Panel
from ktu_tui import (
    build_layout,
    build_header,
    build_sidenav,
    build_statusbar,
    render_snapshot,
)
from ktu_parser import KTUParser
from ktu_client import KTUClient, DASHBOARD_URL, PROFILE_URL, EXAM_URL

console = Console()


def fake_client(logged_in: bool) -> KTUClient:
    c = KTUClient()
    c.logged_in = logged_in
    c.username = "TVE23CS027"
    c.welcome_name = "AMALJITH  V"
    return c


def preview_screen(name: str, html_path: pathlib.Path, url: str) -> None:
    if not html_path.exists():
        console.print(f"[yellow](skip {name} — {html_path} not found)[/yellow]")
        return
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    snap = KTUParser.parse(html)
    if not snap.welcome_user:
        snap.welcome_user = "AMALJITH  V"
    client = fake_client(logged_in=True)
    content_panel = render_snapshot(snap, url)
    layout = build_layout(
        client,
        snap.sidebar_links,
        content_panel,
        current_url=url,
        last_msg="Refreshed 2 seconds ago",
    )
    console.rule(f"[bold cyan]PREVIEW: {name} ({url})[/bold cyan]")
    console.print(layout)
    console.print()


def preview_chrome() -> None:
    console.rule("[bold cyan]PREVIEW: header + sidenav + statusbar (offline)[/bold cyan]")
    client = fake_client(logged_in=False)
    console.print(build_header(client))
    console.print(build_sidenav(client, sub_links=[], current_url=None))
    console.print(build_statusbar(client, last_msg="Ready."))
    console.print()

    console.rule("[bold cyan]PREVIEW: same chrome (online, after refresh)[/bold cyan]")
    client = fake_client(logged_in=True)
    console.print(build_header(client))
    console.print(build_sidenav(client, sub_links=[], current_url=DASHBOARD_URL))
    console.print(build_statusbar(client, last_msg="Refreshed 2 seconds ago"))
    console.print()


def main() -> int:
    pages_dir = pathlib.Path(__file__).parent.parent / "debug" / "pages"
    preview_chrome()
    for name, fname, url in [
        ("DASHBOARD", "dashboard.html", DASHBOARD_URL),
        ("PROFILE", "profile.html", PROFILE_URL),
        ("EXAM DEFS", "exam_definition.html", EXAM_URL),
    ]:
        preview_screen(name, pages_dir / fname, url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
