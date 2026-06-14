"""
Unauthenticated probe of app.ktu.edu.in to learn the architecture.

Goals:
  1. Confirm login form fields, action URL, CSRF handling
  2. Find static assets (JS frameworks, CSS) the site loads
  3. Check for AJAX endpoints that return JSON
  4. Map URL patterns (.htm vs .json, MVC-style paths)
  5. Look at response headers (server, cookies, caching)

Rate limit: one request per second, abort on 403/429.
"""
import time
import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://app.ktu.edu.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

session = requests.Session()
session.headers.update(HEADERS)
session.verify = False

findings = {"base": BASE, "endpoints": [], "assets": [], "forms": [], "headers_sample": {}, "js_libraries": []}


def polite_get(url, label):
    try:
        r = session.get(url, timeout=15, allow_redirects=True)
    except Exception as e:
        return None, {"error": str(e)}
    time.sleep(1.0)  # rate limit
    return r, {
        "url": url,
        "label": label,
        "status": r.status_code,
        "final_url": r.url,
        "history": [h.status_code for h in r.history],
        "content_type": r.headers.get("Content-Type"),
        "server": r.headers.get("Server"),
        "set_cookie": r.headers.get("Set-Cookie"),
        "x-powered-by": r.headers.get("X-Powered-By"),
        "content_length": len(r.text),
    }


# 1. Login page
r, info = polite_get(f"{BASE}/login.htm", "login")
findings["headers_sample"]["login"] = info
if r and r.status_code == 200:
    soup = BeautifulSoup(r.text, "html.parser")
    for form in soup.find_all("form"):
        findings["forms"].append({
            "action": form.get("action"),
            "method": form.get("method", "GET"),
            "id": form.get("id"),
            "inputs": [{"name": i.get("name"), "type": i.get("type"), "value": i.get("value")} for i in form.find_all("input")],
        })
    for script in soup.find_all("script", src=True):
        findings["assets"].append({"type": "js", "url": urljoin(BASE, script["src"])})
    for link in soup.find_all("link", rel="stylesheet"):
        findings["assets"].append({"type": "css", "url": urljoin(BASE, link["href"])})
    # Look for jQuery / framework hints
    for script in soup.find_all("script"):
        if script.string:
            if "jquery" in script.string.lower():
                findings["js_libraries"].append("jQuery (inline reference)")
            if "angular" in script.string.lower():
                findings["js_libraries"].append("Angular (inline reference)")
            if "react" in script.string.lower():
                findings["js_libraries"].append("React (inline reference)")

# 2. robots.txt
r, info = polite_get(f"{BASE}/robots.txt", "robots")
findings["headers_sample"]["robots"] = info
if r and r.status_code == 200:
    findings["robots_txt"] = r.text[:2000]

# 3. Try a known post-login URL without auth — should redirect to login
for path in ["/eu/alt/dashboard.htm", "/eu/exm/viewStudentExamDefinition.htm", "/eu/stu/studentBasicProfile.htm"]:
    r, info = polite_get(f"{BASE}{path}", f"unauth:{path}")
    findings["headers_sample"][f"unauth_{path}"] = info

# 4. Look for common AJAX endpoints (some Spring apps expose .json)
for path in ["/api/", "/eu/", "/login.json", "/home.htm"]:
    r, info = polite_get(f"{BASE}{path}", f"probe:{path}")
    findings["headers_sample"][f"probe_{path}"] = info

with open("/home/workspace/Projects/ktu_tui/debug/public_probe.json", "w") as f:
    json.dump(findings, f, indent=2, default=str)
print(json.dumps(findings, indent=2, default=str))
