"""
Discover all JS files the login page references, and check common locations.
Also pull the full login page HTML for offline analysis.
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
})
session.verify = False

# Save the full login page HTML
r = session.get("https://app.ktu.edu.in/login.htm", timeout=15)
with open("/home/workspace/Projects/ktu_tui/debug/login_page.html", "w", encoding="utf-8") as f:
    f.write(r.text)
print(f"Saved login_page.html ({len(r.text)} bytes)")

soup = BeautifulSoup(r.text, "html.parser")
scripts = []
for s in soup.find_all("script"):
    if s.get("src"):
        scripts.append(urljoin("https://app.ktu.edu.in", s["src"]))
    elif s.string:
        # Inline scripts may contain AJAX
        for url in re.findall(r'["\']((?:/eu|/login|/api)[^"\']*)["\']', s.string):
            scripts.append(f"INLINE_URL: {url}")

print("\n=== All scripts and inline URLs ===")
for s in scripts:
    print(f"  {s}")

# Probe common JS files
for path in ["/js/", "/js/app.js", "/js/main.js", "/js/common.js", "/js/ktu.js", "/js/site.js",
             "/js/validation.js", "/js/login.js", "/js/global.js",
             "/static/", "/webjars/", "/webjars/jquery/"]:
    r = session.get(f"https://app.ktu.edu.in{path}", timeout=10)
    time.sleep(0.5)
    print(f"  {path:35s} -> {r.status_code}  (final: {r.url[-60:]})")
