"""Write a publishable copy of the dashboard with the two live AWS hosts redacted.

The local copy keeps the real addresses -- they are what you need to debug the
stack. This produces the copy that goes to GitHub. Only the text layer is
rewritten; the embedded JPEGs are page viewports (no browser chrome, so no URL
bar), but a page that happens to *print* its own host -- a GitLab clone box, for
instance -- would still carry it, so this is a redaction, not a guarantee.
"""
import json, re, sys
from pathlib import Path

SRC = Path("/local3/yuhan/tmp/a3_webarena_dashboard.html")
DST = Path("/local3/yuhan/tmp/a3dash/public/a3_webarena_dashboard.html")

# The addresses live in an untracked file next to this script, not in it: a
# redaction script that ships the strings it redacts redacts nothing.
#   hosts.local.json  ->  {"<site-ip>": "WEBARENA_HOST", "<map-ip>": "MAP_HOST"}
HOSTS_FILE = Path(__file__).with_name("hosts.local.json")
if not HOSTS_FILE.exists():
    sys.exit(f"missing {HOSTS_FILE} -- see the comment above for its shape")
HOSTS = json.loads(HOSTS_FILE.read_text())

s = SRC.read_text(encoding="utf-8")
# Guard against a substitution that silently does nothing, and against touching
# the base64 payload: neither address can occur there, but assert the count anyway.
b64 = sum(len(m) for m in re.findall(r'base64,[A-Za-z0-9+/=]+', s))
for ip, name in HOSTS.items():
    n = s.count(ip)
    if not n:
        sys.exit(f"{ip} not found -- did the render change?")
    s = s.replace(ip, name)
    print(f"  {ip} -> {name}  ({n} occurrences)")

leftover = set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', re.sub(r'base64,[A-Za-z0-9+/=]+', '', s)))
leftover -= {"127.0.0.1", "0.0.0.0"}
if leftover:
    sys.exit(f"unredacted addresses remain: {sorted(leftover)}")

DST.parent.mkdir(parents=True, exist_ok=True)
DST.write_text(s, encoding="utf-8")
print(f"{DST}  {DST.stat().st_size/1e6:.1f} MB  (base64 payload {b64/1e6:.1f} MB)")
