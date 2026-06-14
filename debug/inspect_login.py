"""
Inspect the login page HTML for architecture hints:
  - Footer links (which suggest more pages)
  - Hidden / commented-out text
  - All forms (in case there are more than one)
  - Any JSON or AJAX wiring
"""
import re
from bs4 import BeautifulSoup

with open("/home/workspace/Projects/ktu_tui/debug/login_page.html") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

print("=== All links on login page ===")
for a in soup.find_all("a", href=True):
    print(f"  {a.get_text(strip=True)[:50]!r:50s} -> {a['href']}")

print("\n=== Images ===")
for img in soup.find_all("img", src=True):
    print(f"  {img.get('alt', 'no-alt')!r:30s} -> {img['src']}")

print("\n=== All form actions ===")
for form in soup.find_all("form"):
    print(f"  id={form.get('id')!r:20s} action={form.get('action')!r:20s} method={form.get('method')!r:10s}")
    for inp in form.find_all(["input", "select", "textarea", "button"]):
        attrs = {k: v for k, v in inp.attrs.items() if k in ("name", "type", "value", "id", "class")}
        print(f"    {inp.name}: {attrs}")

print("\n=== HTML comments (look for hints) ===")
for c in soup.find_all(string=lambda t: isinstance(t, type(soup.new_tag('').string)) and t and '<!--' in str(t)):
    text = str(c).strip()
    if text.startswith('<!--') and text.endswith('-->'):
        if len(text) < 300:
            print(f"  COMMENT: {text}")
        else:
            print(f"  COMMENT (truncated): {text[:200]}...")

# Look for any <script> with non-src content
print("\n=== Inline scripts (first 200 chars) ===")
for s in soup.find_all("script"):
    if s.string and not s.get("src"):
        print(f"  {s.string[:200]!r}")
        print()

# Look for "Powered by" or framework hints
for tag in soup.find_all(["meta", "link"]):
    if tag.get("name") in ("generator", "framework") or "powered" in str(tag).lower():
        print(f"  META: {tag}")
