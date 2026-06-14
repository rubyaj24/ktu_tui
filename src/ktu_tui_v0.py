"""
KTU Portal TUI
==============

A terminal interface for your own KTU e-Gov account (app.ktu.edu.in).

Features:
  - Login via login.htm (session + CSRF handled automatically)
  - View dashboard (eu/alt/dashboard.htm)
  - View exam notifications (eu/exm/viewStudentExamDefinition.htm) — searchable
    by academic year code and exam type
  - View basic profile details (eu/stu/studentBasicProfile.htm)
  - Generic "fetch any page" mode to explore other pages and parse tables
  - Re-login if session expires

Requirements:
  pip install requests beautifulsoup4 rich

Run:
  python ktu_tui.py

NOTE: This tool is intended for accessing YOUR OWN account data only.
Credentials are kept in memory for the session and are never written to disk.
"""

import sys
import getpass

import requests
from bs4 import BeautifulSoup
import urllib3

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.align import Align

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://app.ktu.edu.in"
LOGIN_URL = f"{BASE_URL}/login.htm"
DASHBOARD_URL = f"{BASE_URL}/eu/alt/dashboard.htm"
EXAM_URL = f"{BASE_URL}/eu/exm/viewStudentExamDefinition.htm"
PROFILE_URL = f"{BASE_URL}/eu/stu/studentBasicProfile.htm"

console = Console()


class KTUClient:
    """Handles authentication and page fetching for the KTU portal."""

    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Referer": LOGIN_URL,
        })
        self.logged_in = False
        self.username = None

    def get_csrf_token(self):
        res = self.session.get(LOGIN_URL)
        soup = BeautifulSoup(res.text, "html.parser")
        token_input = soup.find("input", {"name": "CSRF_TOKEN"})
        if not token_input:
            raise RuntimeError("Could not find CSRF_TOKEN on login page.")
        return token_input["value"]

    def login(self, username, password, debug=False):
        csrf = self.get_csrf_token()
        res = self.session.post(
            LOGIN_URL,
            data={
                "username": username,
                "password": password,
                "CSRF_TOKEN": csrf,
            },
            allow_redirects=True,
        )

        if "Invalid username or password" in res.text:
            return False, "Invalid username or password."

        # Verify success by checking whether the dashboard is reachable
        # without being bounced back to the login form.
        verify = self.session.get(DASHBOARD_URL)

        if debug:
            console.print(f"[dim]DEBUG: login status_code = {res.status_code}, final URL = {res.url}[/dim]")
            console.print(f"[dim]DEBUG: dashboard check status_code = {verify.status_code}, final URL = {verify.url}[/dim]")
            console.print(f"[dim]DEBUG: dashboard still shows login form = {self._is_login_page(verify.text)}[/dim]")

        if self._is_login_page(verify.text):
            return False, (
                "Login did not succeed — dashboard redirected back to the "
                "login form. Check your username/password and try again."
            )

        self.logged_in = True
        self.username = username
        return True, "Login successful."

    @staticmethod
    def _is_login_page(html):
        """True only for the actual login page, not just any page with a CSRF token."""
        return 'id="login-username"' in html and 'name="loginform"' in html

    def fetch(self, url):
        """Fetch a page, returning (ok, html_or_error)."""
        if not self.logged_in:
            return False, "Not logged in."

        res = self.session.get(url)

        if self._is_login_page(res.text):
            self.logged_in = False
            return False, "Session expired — please log in again."

        return True, res.text

    def fetch_exam_notifications(self, academic_year="96", exam_type=""):
        """POST the exam definition search form and return the results page."""
        if not self.logged_in:
            return False, "Not logged in."

        # Load the page first to pick up any CSRF token / hidden fields the
        # search form requires.
        res = self.session.get(EXAM_URL)

        if self._is_login_page(res.text):
            self.logged_in = False
            return False, "Session expired — please log in again."

        soup = BeautifulSoup(res.text, "html.parser")
        data = {
            "form_name": "searchForm",
            "academicYear": academic_year,
            "examType": exam_type,
        }

        csrf_input = soup.find("input", {"name": "CSRF_TOKEN"})
        if csrf_input:
            data["CSRF_TOKEN"] = csrf_input["value"]

        res2 = self.session.post(EXAM_URL, data=data)

        if self._is_login_page(res2.text):
            self.logged_in = False
            return False, "Session expired — please log in again."

        return True, res2.text

    @staticmethod
    def parse_tables(html):
        """Extract all <table> elements as list of (headers, rows)."""
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            rows = []
            for tr in table.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cols:
                    rows.append(cols)
            if rows:
                results.append((headers, rows))
        return results

    @staticmethod
    def parse_list_items(html):
        """Extract Bootstrap list-group items as (title, description) pairs."""
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for item in soup.find_all("a", class_="list-group-item"):
            title = item.find(["h3", "h4", "strong"])
            desc = item.find("p")
            if title:
                items.append((
                    title.get_text(strip=True),
                    desc.get_text(strip=True) if desc else "",
                ))
        return items


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def banner():
    console.clear()
    console.print(Panel(
        Align.center(Text("KTU PORTAL — TERMINAL CLIENT", style="bold cyan")),
        border_style="cyan",
    ))


def login_screen(client):
    while True:
        banner()
        console.print(Panel("[bold]Sign in to app.ktu.edu.in[/bold]", border_style="blue"))
        username = Prompt.ask("Username")
        password = getpass.getpass("Password: ")

        with console.status("[cyan]Logging in..."):
            try:
                ok, msg = client.login(username, password, debug=True)
            except Exception as e:
                ok, msg = False, f"Error: {e}"

        if ok:
            console.print(f"[bold green]{msg}[/bold green] Welcome, {username}.")
            return True

        console.print(f"[bold red]{msg}[/bold red]")
        retry = Prompt.ask("Try again? (y/n)", choices=["y", "n"], default="y")
        if retry == "n":
            return False


def render_tables(html, title):
    tables = KTUClient.parse_tables(html)
    items = KTUClient.parse_list_items(html)

    if not tables and not items:
        console.print(Panel(
            "No structured table/list data found on this page.\n"
            "The page may use a different layout — try 'Custom page' "
            "and inspect the raw HTML if needed.",
            title=title, border_style="yellow",
        ))
        return

    for headers, rows in tables:
        table = Table(title=title, show_lines=True, border_style="green")
        if headers:
            for h in headers:
                table.add_column(h, overflow="fold")
        else:
            for i in range(len(rows[0])):
                table.add_column(f"Col {i+1}", overflow="fold")
        for row in rows:
            table.add_row(*row)
        console.print(table)

    if items:
        table = Table(title=f"{title} (list items)", show_lines=True, border_style="green")
        table.add_column("Title", style="bold")
        table.add_column("Details", overflow="fold")
        for t, d in items:
            table.add_row(t, d)
        console.print(table)


def view_dashboard(client):
    banner()
    with console.status("[cyan]Fetching dashboard..."):
        ok, html = client.fetch(DASHBOARD_URL)

    if not ok:
        console.print(f"[bold red]{html}[/bold red]")
        return ok

    render_tables(html, "Dashboard")
    return True


def view_exam_notifications(client):
    banner()
    console.print(Panel(
        "Exam Definitions Search\n"
        "Academic Year codes: 96 = 2025-26 (enter the code shown on the portal's dropdown)\n"
        "Exam Type: leave blank for all types",
        border_style="blue",
    ))
    academic_year = Prompt.ask("Academic Year code", default="96")
    exam_type = Prompt.ask("Exam Type (blank = all)", default="")

    with console.status("[cyan]Fetching exam notifications..."):
        ok, html = client.fetch_exam_notifications(academic_year, exam_type)

    if not ok:
        console.print(f"[bold red]{html}[/bold red]")
        return ok

    render_tables(html, "Exam Notifications")
    return True


def view_profile(client):
    banner()
    with console.status("[cyan]Fetching profile..."):
        ok, html = client.fetch(PROFILE_URL)

    if not ok:
        console.print(f"[bold red]{html}[/bold red]")
        return ok

    render_tables(html, "Profile Details")
    return True


def custom_page(client):
    banner()
    console.print(Panel(
        "Enter the full URL of any page on app.ktu.edu.in you'd like to fetch\n"
        "(e.g. https://app.ktu.edu.in/eu/std/someEndpoint.htm)",
        border_style="blue",
    ))
    url = Prompt.ask("URL")

    with console.status("[cyan]Fetching page..."):
        ok, html = client.fetch(url)

    if not ok:
        console.print(f"[bold red]{html}[/bold red]")
        return ok

    render_tables(html, url)

    show_raw = Prompt.ask("Save raw HTML to file for inspection? (y/n)", choices=["y", "n"], default="n")
    if show_raw == "y":
        fname = "ktu_page_dump.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
        console.print(f"[green]Saved to {fname}[/green]")

    return True


def main_menu(client):
    while True:
        banner()
        console.print(Panel(f"[bold]Logged in as:[/bold] {client.username}", border_style="cyan"))

        table = Table(show_header=False, border_style="bright_blue")
        table.add_column(justify="right", style="bold cyan", width=4)
        table.add_column()
        table.add_row("1", "View Dashboard")
        table.add_row("2", "View Exam Notifications")
        table.add_row("3", "View Profile Details")
        table.add_row("4", "Custom page (fetch any KTU page)")
        table.add_row("5", "Re-login")
        table.add_row("0", "Quit")
        console.print(table)

        choice = Prompt.ask("Select an option", choices=["0", "1", "2", "3", "4", "5"], default="1")

        if choice == "1":
            ok = view_dashboard(client)
        elif choice == "2":
            ok = view_exam_notifications(client)
        elif choice == "3":
            ok = view_profile(client)
        elif choice == "4":
            ok = custom_page(client)
        elif choice == "5":
            client.logged_in = False
            return  # back to login
        elif choice == "0":
            console.print("[bold cyan]Goodbye![/bold cyan]")
            sys.exit(0)
        else:
            ok = True

        if not ok and not client.logged_in:
            console.print("[yellow]Returning to login...[/yellow]")
            return

        Prompt.ask("\nPress Enter to continue", default="", show_default=False)


def main():
    client = KTUClient()
    try:
        while True:
            if not login_screen(client):
                break
            main_menu(client)
    except KeyboardInterrupt:
        console.print("\n[bold cyan]Goodbye![/bold cyan]")


if __name__ == "__main__":
    main()