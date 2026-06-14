"""
Download and inspect jQuery + theme.js to find AJAX endpoints.
Government portals often hardcode the API surface in static JS.
"""
import re
import time
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
})
session.verify = False

# Pull jQuery to confirm version, then grab theme.js
for path in ["/js/jquery-1.11.3.min.js", "/js/theme.js"]:
    r = session.get(f"https://app.ktu.edu.in{path}", timeout=15)
    time.sleep(0.8)
    if r.status_code == 200:
        fname = f"/home/workspace/Projects/ktu_tui/debug/{path.split('/')[-1]}"
        with open(fname, "w", encoding="utf-8", errors="ignore") as f:
            f.write(r.text)
        print(f"Saved {fname} ({len(r.text)} bytes)")

# Find AJAX-ish URLs in theme.js
import os
theme_path = "/home/workspace/Projects/ktu_tui/debug/theme.js"
if os.path.exists(theme_path):
    with open(theme_path) as f:
        content = f.read()
    ajax_calls = re.findall(r'\$\.(?:get|post|ajax)\s*\(\s*["\']([^"\']+)["\']', content)
    urls = re.findall(r'["\']((?:/eu|/login)[^"\']+)["\']', content)
    print("\n=== AJAX calls in theme.js ===")
    for u in set(ajax_calls):
        print(f"  {u}")
    print("\n=== /eu /login URLs in theme.js ===")
    for u in sorted(set(urls))[:30]:
        print(f"  {u}")
