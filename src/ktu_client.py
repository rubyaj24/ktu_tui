"""
KTUClient — low-level HTTP/auth client for app.ktu.edu.in  (v0.3)

Design notes
------------
The portal is a server-rendered Spring MVC web app served behind an
AWS Application Load Balancer (ALB).  Every data page is in the
response body — there is no AJAX hydration needed for our purposes
(though the dashboard does JS-hydrate some panels, the *HTML shell*
is complete).

Auth model
----------
* POST to /login.htm with {username, password, CSRF_TOKEN}.
* The server issues a JSESSIONID cookie.
* Subsequent requests carry that cookie + CSRF_TOKEN on form POSTs.
* /logout.htm destroys the session.

Rate limiting
-------------
Token bucket: 1 req/s steady state, burst 3.  This keeps us under
the ALB's 5 req/s per IP cap with margin to spare, and looks like
normal human traffic.

Spinner behavior
----------------
The portal renders a `<div id="loader">` overlay in the HTML, and a
small inline script hides it when the *browser* finishes loading
external assets.  This is a pure browser-side visual effect; the
server response is complete.  No retry needed.  (v0.2's spinner
retry was based on a wrong assumption — we now just return what we
got.)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import re
import requests
import urllib3

from bs4 import BeautifulSoup

from ktu_parser import KTUParser, PageSnapshot

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://app.ktu.edu.in"
LOGIN_URL = f"{BASE_URL}/login.htm"
LOGOUT_URL = f"{BASE_URL}/logout.htm"

# Default endpoints the TUI exposes.
DASHBOARD_URL = f"{BASE_URL}/eu/alt/dashboard.htm"
EXAM_URL = f"{BASE_URL}/eu/exm/viewStudentExamDefinition.htm"
PROFILE_URL = f"{BASE_URL}/eu/stu/studentBasicProfile.htm"
STUDENT_DETAILS_URL = f"{BASE_URL}/eu/stu/studentDetailsView.htm"
PENDING_RESULTS_URL = f"{BASE_URL}/eu/res/pendingResults.htm"
SEMESTER_GRADE_CARD_URL = f"{BASE_URL}/eu/res/semesterGradeCardListing.htm"
CERTIFICATES_URL = f"{BASE_URL}/eu/stu/req/studentCertificatesListing.htm"
FEES_URL = f"{BASE_URL}/eu/stu/studentFeeListing.htm"
ATTENDANCE_URL = f"{BASE_URL}/eu/acd/studentSemesterListing.htm"
ELIGIBILITY_URL = f"{BASE_URL}/eu/exm/studentEligibilityView.htm"
TICKETS_URL = f"{BASE_URL}/eu/tkt/listRequesterTicketRequest.htm"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# -----------------------------------------------------------------------
# Rate limiter (token bucket)
# -----------------------------------------------------------------------


class TokenBucket:
    """Thread-safe token bucket.

    capacity = max tokens that can accumulate.
    refill_rate = tokens per second.
    """

    def __init__(self, capacity: int = 3, refill_rate: float = 1.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.lock = threading.Lock()
        self.last_refill = time.monotonic()

    def take(self, n: int = 1) -> None:
        """Block until n tokens are available, then consume them."""
        with self.lock:
            while True:
                self._refill()
                if self.tokens >= n:
                    self.tokens -= n
                    return
                # How long until we have n tokens?
                deficit = n - self.tokens
                wait = deficit / self.refill_rate
                # Release the lock while we wait.
                self.lock.release()
                try:
                    time.sleep(wait)
                finally:
                    self.lock.acquire()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now


# -----------------------------------------------------------------------
# Page result
# -----------------------------------------------------------------------


@dataclass
class PageResult:
    ok: bool
    status: int
    url: str
    final_url: str
    error: Optional[str] = None
    html: Optional[str] = None
    snapshot: Optional[PageSnapshot] = None
    is_login_page: bool = False

    @classmethod
    def from_response(cls, res: requests.Response, ok: bool = True, error: Optional[str] = None) -> "PageResult":
        html = res.text if res is not None else None
        snap = KTUParser.parse(html) if html else None
        is_login = bool(html) and KTUParser.is_login_page(html)
        return cls(
            ok=ok,
            status=res.status_code if res is not None else 0,
            url=res.url if res is not None else "",
            final_url=res.url if res is not None else "",
            error=error,
            html=html,
            snapshot=snap,
            is_login_page=is_login,
        )


# -----------------------------------------------------------------------
# Logger
# -----------------------------------------------------------------------


log = logging.getLogger("ktu")


# -----------------------------------------------------------------------
# Client
# -----------------------------------------------------------------------


class KTUClient:
    """Stateful session-based client for the KTU portal."""

    def __init__(self, rate_per_sec: float = 1.0, burst: int = 3):
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
        })
        self.bucket = TokenBucket(capacity=burst, refill_rate=rate_per_sec)
        self.logged_in = False
        self.username: Optional[str] = None
        self.welcome_name: Optional[str] = None

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Rate-limited request."""
        self.bucket.take()
        try:
            res = self.session.request(method, url, timeout=30, **kwargs)
            log.info("%s %s -> %d", method, url, res.status_code)
            return res
        except requests.RequestException as e:
            log.error("%s %s failed: %s", method, url, e)
            return None

    @staticmethod
    def _extract_csrf(html: str) -> Optional[str]:
        """Find the first CSRF_TOKEN input value in `html`."""
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("input", attrs={"name": "CSRF_TOKEN"})
        return tag["value"] if tag and tag.has_attr("value") else None

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def fetch_login_page(self) -> PageResult:
        res = self._request("GET", LOGIN_URL, allow_redirects=True)
        if res is None:
            return PageResult(ok=False, status=0, url=LOGIN_URL, final_url=LOGIN_URL,
                              error="Network error reaching login page.")
        return PageResult.from_response(res)

    def login(self, username: str, password: str) -> PageResult:
        """Attempt to log in.  Returns a PageResult; check .ok and .snapshot."""
        # Step 1: fetch login page to obtain CSRF token.
        login_page = self.fetch_login_page()
        if not login_page.ok or not login_page.html:
            return PageResult(
                ok=False, status=login_page.status,
                url=LOGIN_URL, final_url=LOGIN_URL,
                error=f"Could not fetch login page: {login_page.error}",
            )

        csrf = self._extract_csrf(login_page.html)
        if not csrf:
            return PageResult(
                ok=False, status=login_page.status,
                url=LOGIN_URL, final_url=LOGIN_URL,
                error="Login page did not contain a CSRF_TOKEN. "
                      "The portal may be down or the URL has changed.",
            )

        # Step 2: POST credentials.  Note: the response *body* doesn't
        # tell us much — Spring Security sends a 302 redirect to the
        # originally-requested URL (or /home.htm).  We follow it then
        # verify with a real authenticated request.
        self.session.headers["Referer"] = LOGIN_URL
        res = self._request(
            "POST",
            LOGIN_URL,
            data={
                "username": username,
                "password": password,
                "CSRF_TOKEN": csrf,
            },
            allow_redirects=True,
        )
        if res is None:
            return PageResult(ok=False, status=0, url=LOGIN_URL, final_url=LOGIN_URL,
                              error="Network error during login POST.")

        # If the response body itself shows an error, surface it.
        if "Invalid username or password" in res.text:
            return PageResult.from_response(
                res, ok=False, error="Invalid username or password."
            )

        # Step 3: verify by hitting the dashboard.  The dashboard will
        # render fully if the session is valid, or bounce to the login
        # page (with LOGIN_URL in `res.url`) if not.
        verify = self._request("GET", DASHBOARD_URL, allow_redirects=True)
        if verify is None:
            return PageResult(ok=False, status=0, url=DASHBOARD_URL,
                              final_url=DASHBOARD_URL,
                              error="Network error verifying login.")

        result = PageResult.from_response(verify)

        if result.is_login_page:
            return PageResult(
                ok=False,
                status=result.status,
                url=DASHBOARD_URL,
                final_url=result.final_url,
                error="Login did not succeed. The dashboard redirected back "
                      "to the login form. Check username/password.",
                html=verify.text,
                snapshot=result.snapshot,
                is_login_page=True,
            )

        # Authenticated.
        self.logged_in = True
        self.username = username
        self.welcome_name = KTUParser.extract_welcome(verify.text) or username
        return PageResult.from_response(verify)

    def logout(self) -> None:
        if self.logged_in:
            self._request("GET", LOGOUT_URL, allow_redirects=True)
        self.session.cookies.clear()
        self.logged_in = False
        self.username = None
        self.welcome_name = None

    def fetch(self, url: str, method: str = "GET", data: Optional[dict] = None) -> PageResult:
        """Generic page fetch."""
        if not self.logged_in:
            return PageResult(ok=False, status=0, url=url, final_url=url,
                              error="Not logged in.")

        kwargs: dict = {"allow_redirects": True}
        if method == "POST":
            kwargs["data"] = data or {}

        res = self._request(method, url, **kwargs)
        if res is None:
            return PageResult(ok=False, status=0, url=url, final_url=url,
                              error="Network error.")
        return PageResult.from_response(res)

    def fetch_exam_notifications(self, academic_year: str = "97",
                                 exam_type: str = "") -> PageResult:
        """POST the exam definition search form.  Returns the rendered page.

        academic_year is a portal-internal code (e.g. 97 = 2026-27).
        exam_type is one of: "" (all), 1 (End Semester), 2 (Supplementary),
        3 (Honours), 4 (Contact Class), 5 (Minor), 6 (Challenge).
        """
        if not self.logged_in:
            return PageResult(ok=False, status=0, url=EXAM_URL, final_url=EXAM_URL,
                              error="Not logged in.")

        # First GET the page so we have its CSRF token + form_name.
        first = self.fetch(EXAM_URL)
        if not first.ok:
            return first
        if not first.html:
            return PageResult(ok=False, status=first.status, url=EXAM_URL,
                              final_url=first.final_url, error="Empty response.")

        csrf = self._extract_csrf(first.html)
        payload = {
            "form_name": "searchForm",
            "CSRF_TOKEN": csrf,
            "academicYear": academic_year,
            "examType": exam_type,
        }
        return self.fetch(EXAM_URL, method="POST", data=payload)

    def fetch_semester_grade_card(self, semester_id: str) -> PageResult:
        """POST the semester grade card listing form.

        semester_id is a portal code (e.g. '5' for S5).
        """
        if not self.logged_in:
            return PageResult(ok=False, status=0, url=SEMESTER_GRADE_CARD_URL,
                              final_url=SEMESTER_GRADE_CARD_URL,
                              error="Not logged in.")

        first = self.fetch(SEMESTER_GRADE_CARD_URL)
        if not first.ok:
            return first
        if not first.html:
            return PageResult(ok=False, status=first.status, url=SEMESTER_GRADE_CARD_URL,
                              final_url=first.final_url, error="Empty response.")

        csrf = self._extract_csrf(first.html)
        payload = {
            "form_name": "changePasswordForm",
            "CSRF_TOKEN": csrf,
            "semesterId": semester_id,
        }
        return self.fetch(SEMESTER_GRADE_CARD_URL, method="POST", data=payload)
