"""
KTU HTML parser — v0.3

What we know about the portal's HTML, learned from real pages:

  * Pages have a `<div id="loader">` + `<div id="spinner">` at the top of
    <body>.  A small inline `<script>` hides them once `document.readyState
    == "complete"`.  The script is a visual effect only — the page body
    is fully present in the HTTP response.  **No retry is needed** for
    "spinner only" responses; that was a wrong assumption in v0.2.

  * Authenticated pages have a navbar item like
    `<span class="tooltiptext">Welcome AMALJITH V</span>`.  Login pages
    don't have it.  This is the most reliable auth marker.

  * The profile page is a Bootstrap 3 `list-group` with `<li class=
    "list-group-item">` and a `<span class="view-badge">LABEL</span>` for
    the key and the rest of the text as the value.  v0.2 only handled
    `<a class="list-group-item">`, which is a *different* component
    (the dashboard alerts list).

  * The exam page has a search form (`<form name="searchForm">`) with
    `<select name="academicYear">` and `<select name="examType">`.  The
    dropdowns auto-submit on change, so the search is implemented as a
    full POST round-trip.

  * "No results" is rendered as `<div class="alert alert-info">No exam
    definition for selected academic year.</div>`.  We surface these as
    empty result messages, not parser failures.

  * The dashboard is a JS-rendered shell: panel headers are present
    ("Welcome", "Fee Details", "Suraksha", "Alerts", "Feedback Form")
    but the body divs are empty in HTML — filled by `/js/alt/dashboard.js`
    at runtime.  We can extract the *section titles* but not the values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from bs4 import BeautifulSoup, Tag


# -----------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------


@dataclass
class KVRow:
    """A single key-value pair (used for profile-style pages)."""

    key: str
    value: str


@dataclass
class ListItem:
    """A Bootstrap list-group item."""

    title: str
    description: str = ""


@dataclass
class SidebarLink:
    """A link extracted from a page's left navigation sidebar.

    `is_current` is True when the portal's HTML marks this link as the
    active page (e.g. via `class="active"` on the <a> or its <li>).
    """

    url: str
    text: str
    is_current: bool = False


@dataclass
class TableBlock:
    """A single HTML <table> as headers + rows."""

    headers: List[str]
    rows: List[List[str]]


@dataclass
class PageSnapshot:
    """Everything we could extract from one page."""

    title: str = ""
    welcome_user: Optional[str] = None
    alerts: List[str] = field(default_factory=list)
    panel_titles: List[str] = field(default_factory=list)
    list_items: List[ListItem] = field(default_factory=list)
    kv_blocks: List[List[KVRow]] = field(default_factory=list)
    tables: List[TableBlock] = field(default_factory=list)
    empty_messages: List[str] = field(default_factory=list)
    form_options: dict = field(default_factory=dict)
    logout_url: Optional[str] = None
    sidebar_links: List[SidebarLink] = field(default_factory=list)

    @property
    def has_anything(self) -> bool:
        return any([
            self.welcome_user,
            self.alerts,
            self.panel_titles,
            self.list_items,
            self.kv_blocks,
            self.tables,
            self.empty_messages,
            self.form_options,
        ])


# -----------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------


class KTUParser:
    """Extracts structured data from a KTU portal HTML page."""

    # The exact markers that appear only on the actual login form.
    LOGIN_FORM_MARKERS = [
        'id="login-username"',
        'id="login-password"',
        'id="btn-login"',  # or the old 'id="login-form-btn"'
    ]

    @staticmethod
    def is_login_page(html: str) -> bool:
        """Return True if `html` looks like the actual login page.

        Note: the substring `name="loginform"` is too loose because
        Spring Security's logout form has that attribute and is rendered
        on every authenticated page.  We require at least 2 of the
        3 markers above (login-username, login-password, btn-login).
        """
        hits = sum(1 for m in KTUParser.LOGIN_FORM_MARKERS if m in html)
        return hits >= 2

    @staticmethod
    def parse(html: str) -> PageSnapshot:
        soup = BeautifulSoup(html, "html.parser")
        snap = PageSnapshot()

        # --- <title> -----------------------------------------------------
        t = soup.find("title")
        if t:
            snap.title = t.get_text(strip=True)

        # --- Welcome name (only on authenticated pages) -----------------
        # The navbar has <span class="tooltiptext">Welcome AMALJITH V</span>
        welcome_span = soup.find("span", class_="tooltiptext")
        if welcome_span:
            text = welcome_span.get_text(" ", strip=True)
            m = re.match(r"^Welcome\s+(.+)$", text, re.I)
            if m:
                snap.welcome_user = m.group(1).strip()

        # --- Logout link -------------------------------------------------
        logout_a = soup.find("a", href=re.compile(r"/logout\.htm"))
        if logout_a:
            snap.logout_url = logout_a["href"]

        # --- Bootstrap alert-* messages ---------------------------------
        # These are how the portal shows empty results + server errors.
        for alert in soup.find_all("div", class_=re.compile(r"^alert(-|$)")):
            cls = " ".join(alert.get("class") or [])
            text = alert.get_text(" ", strip=True)
            if not text:
                continue
            if "alert-danger" in cls:
                snap.empty_messages.append(f"[!] {text}")
            elif "alert-info" in cls:
                snap.empty_messages.append(f"[i] {text}")
            elif "alert-warning" in cls:
                snap.empty_messages.append(f"[w] {text}")
            elif "alert-success" in cls:
                snap.empty_messages.append(f"[OK] {text}")
            else:
                snap.empty_messages.append(text)

        # --- Panel section titles ---------------------------------------
        # Used by the dashboard shell: <div class="panel-heading">
        #   <h3 class="panel-title">Welcome</h3> ...
        # We only collect *headings* (not bodies) because dashboard
        # bodies are JS-populated and empty in HTML.
        for ph in soup.find_all("div", class_="panel-heading"):
            title_tag = ph.find(["h3", "h4", "h2"])
            if title_tag:
                title = title_tag.get_text(strip=True)
                if title and title not in snap.panel_titles:
                    snap.panel_titles.append(title)

        # --- <ul class="list-group"> key/value blocks --------------------
        # Profile page pattern: <li class="list-group-item">
        #   <span class="view-badge">Gender</span> Male
        # Dashboard alerts pattern: <a class="list-group-item"> ... </a>
        for ul in soup.find_all("ul", class_="list-group"):
            block: List[KVRow] = []
            for li in ul.find_all("li", class_="list-group-item", recursive=False):
                badge = li.find("span", class_="view-badge")
                if badge:
                    key = badge.get_text(strip=True).rstrip(":")
                    # value is everything in <li> *except* the badge
                    value = li.get_text(" ", strip=True)
                    if badge.get_text(strip=True):
                        value = value.replace(badge.get_text(strip=True), "", 1).strip()
                    block.append(KVRow(key=key, value=value))
                else:
                    text = li.get_text(" ", strip=True)
                    if text:
                        snap.list_items.append(ListItem(title=text))
            if block:
                # Drop rows whose key is portal noise (anti-ragging,
                # password-change, etc) or whose value is empty/placeholder.
                block = [
                    row for row in block
                    if not _is_noise_key(row.key)
                    and not _is_empty_value(row.value)
                ]
                if block:
                    snap.kv_blocks.append(block)

        # Standalone <a class="list-group-item"> blocks
        for a in soup.find_all("a", class_="list-group-item"):
            title_tag = a.find(["h3", "h4", "strong"])
            desc_tag = a.find("p")
            if title_tag:
                snap.list_items.append(ListItem(
                    title=title_tag.get_text(strip=True),
                    description=desc_tag.get_text(strip=True) if desc_tag else "",
                ))

        # --- <table> elements -------------------------------------------
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            rows: List[List[str]] = []
            for tr in table.find_all("tr"):
                cols = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if cols:
                    rows.append(cols)
            # Keep tables with rows OR with headers (an empty results
            # table is still informative — the page told us the structure)
            if rows or headers:
                snap.tables.append(TableBlock(headers=headers, rows=rows))

        # --- <select> options -------------------------------------------
        # Used for the exam definition form: we want the user to be able
        # to pick year "97 = 2026 - 2027" without having to memorise it.
        for sel in soup.find_all("select"):
            name = sel.get("name")
            if not name:
                continue
            opts = []
            for opt in sel.find_all("option"):
                value = opt.get("value", "")
                label = opt.get_text(strip=True)
                selected = opt.has_attr("selected")
                opts.append({"value": value, "label": label, "selected": selected})
            snap.form_options[name] = opts

        # --- Sidebar navigation links -----------------------------------
        snap.sidebar_links = KTUParser.find_sidebar_links(soup)

        return snap

    # -------------------------------------------------------------------
    # Convenience extractors
    # -------------------------------------------------------------------

    @staticmethod
    def extract_logout_url(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        a = soup.find("a", href=re.compile(r"/logout\.htm"))
        return a["href"] if a else None

    @staticmethod
    def extract_welcome(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        span = soup.find("span", class_="tooltiptext")
        if not span:
            return None
        text = span.get_text(" ", strip=True)
        m = re.match(r"^Welcome\s+(.+)$", text, re.I)
        return m.group(1).strip() if m else None

    # -------------------------------------------------------------------
    # Sidebar link extraction
    # -------------------------------------------------------------------
    #
    # Several KTU pages have a left navigation sidebar.  The container
    # class varies a bit (we've seen `sidebar`, `left-sidebar`, and the
    # generic Bootstrap `nav`/`list-group` inside an aside).  We try
    # several selectors and return whatever looks most like a nav.
    #
    # A "current page" link is detected by the presence of `class="
    # active"` on the <a> or its parent <li>.

    _SIDEBAR_SELECTORS = [
        "div.sidebar",
        "div.left-sidebar",
        "aside.sidebar",
        "ul.sidebar-nav",
        "div#sidebar",
        "ul.nav.nav-pills.nav-stacked",  # common Bootstrap vertical nav
        "ul.nav-tabs",  # sometimes vertical tabs are used as nav
    ]

    @staticmethod
    def find_sidebar(soup: BeautifulSoup) -> Optional[Tag]:
        for sel in KTUParser._SIDEBAR_SELECTORS:
            el = soup.select_one(sel)
            if el:
                return el
        return None

    @staticmethod
    def find_sidebar_links(soup: BeautifulSoup) -> List[SidebarLink]:
        container = KTUParser.find_sidebar(soup)
        if not container:
            return []
        links: List[SidebarLink] = []
        for a in container.find_all("a"):
            href = a.get("href")
            text = a.get_text(" ", strip=True)
            if not href or not text:
                continue
            is_current = False
            if a.get("class") and "active" in a.get("class", []):
                is_current = True
            parent = a.parent
            if parent and parent.get("class") and "active" in parent.get("class", []):
                is_current = True
            links.append(SidebarLink(url=href, text=text, is_current=is_current))
        # Dedup (same href+text), preserve order
        seen = set()
        unique = []
        for l in links:
            key = (l.url, l.text)
            if key not in seen:
                seen.add(key)
                unique.append(l)
        return unique

    @staticmethod
    def extract_sidebar_links(html: str) -> List[SidebarLink]:
        soup = BeautifulSoup(html, "html.parser")
        return KTUParser.find_sidebar_links(soup)


# -------------------------------------------------------------------
# Noise filters
# -------------------------------------------------------------------

# Profile labels that are portal call-to-actions or admin links, not
# personal data.  These appear in the broader profile view (or in some
# sub-pages) as list-group items or buttons.
_NOISE_KEYS = {
    # Direct match
    "anti-ragging", "anti ragging",
    # Substrings
    "ragging", "fill now", "fill-now",
    "password", "password-change", "change password",
    "captcha", "otp", "verification",
    "logout", "sign out",
    "feedback form", "feedback",
}

# Values that mean "no real data" — drop the row rather than show
# empty cells to the user.
_EMPTY_VALUES = {"", "-", "na", "n/a", "none", "null", "nil"}


def _is_noise_key(key: str) -> bool:
    k = (key or "").strip().lower()
    return any(nk in k for nk in _NOISE_KEYS)


def _is_empty_value(val: str) -> bool:
    return (val or "").strip().lower() in _EMPTY_VALUES