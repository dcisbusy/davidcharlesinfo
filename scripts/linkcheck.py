"""Find dead outside links in old posts and look up Internet Archive (Wayback Machine) copies.

Runs in GitHub Actions (.github/workflows/link-check.yml), monthly or by hand. Writes
data/dead-links.json:

    {"https://dead.example/page": {"archive": "https://web.archive.org/web/2012.../https://dead.example/page",
                                   "status": "404", "checked": "2026-11-14"}}

The build then points those links (and images) at the archived copy. A link only counts as dead on a
clear signal: the domain no longer exists, the connection is refused, or the page says 404/410 Not found
or Gone. Sites that block robots (403, 429, 5xx) or time out are left alone. Links already marked dead
are re-checked only if they have no archive copy yet, so a page that comes back to life stays archived.
Delete an entry from the JSON to have it checked again.
"""
import concurrent.futures as cf
import datetime
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = "data/dead-links.json"
SKIP_HOSTS = re.compile(r"(^|\.)(davidcharles\.info|davidcharles\.substack\.com|substackcdn\.com|cdn\.substack\.com|"
                        r"substack-post-media\.s3\.amazonaws\.com|bucketeer-[\w-]+\.s3\.amazonaws\.com|"
                        r"twitter\.com|x\.com|facebook\.com|instagram\.com|linkedin\.com|web\.archive\.org|"
                        r"archive\.org|youtube\.com|youtube-nocookie\.com|youtu\.be|google\.[a-z.]+|"
                        r"googleusercontent\.com|paypal\.me|paypal\.com|amazon\.[a-z.]+|amzn\.to)$", re.I)
UA = "Mozilla/5.0 (compatible; davidcharles.info link checker; +https://davidcharles.info)"
CTX = ssl.create_default_context()


def collect(known_originals=()):
    """Every outside link and image in post content, with the date of the earliest post using it."""
    entries = json.load(open("blog-archive/index.json", encoding="utf-8"))
    first = {}
    for e in entries:
        path = e["url"].strip("/") + "/index.html"
        if not os.path.exists(path):
            continue
        m = re.search(r"<!--content:start-->(.*?)<!--content:end-->", open(path, encoding="utf-8").read(), re.S)
        if not m:
            continue
        for u in re.findall(r'(?:href|src)="(https?://[^"\s]+)"', m.group(1)):
            u = u.replace("&amp;", "&")
            # a link the build already swapped for an archive copy: track the original
            arc = re.match(r"https://web\.archive\.org/web/\d+(?:im_)?/(https?://.+)$", u)
            if arc and arc.group(1) in known_originals:
                u = arc.group(1)
            host = urllib.parse.urlsplit(u).hostname or ""
            if SKIP_HOSTS.search(host):
                continue
            d = (e.get("date") or "2015-01-01")[:10]
            first[u] = min(first.get(u, d), d)
    return first


def check(url):
    """'ok', or the reason it is dead ('dns', 'refused', '404', '410'), or 'unknown'."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
                return "ok" if r.status < 400 else str(r.status)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                if method == "HEAD":
                    continue          # some servers answer HEAD wrongly; confirm with GET
                return str(e.code)
            if e.code in (405, 501) and method == "HEAD":
                continue
            return "ok" if e.code < 400 else "unknown"
        except urllib.error.URLError as e:
            reason = e.reason
            if isinstance(reason, socket.gaierror):
                # double-check the name really doesn't resolve
                try:
                    socket.getaddrinfo(urllib.parse.urlsplit(url).hostname, 443)
                    return "unknown"
                except socket.gaierror:
                    return "dns"
            if isinstance(reason, ConnectionRefusedError):
                return "refused"
            return "unknown"
        except Exception:
            return "unknown"
    return "unknown"


def wayback(url, date):
    q = urllib.parse.urlencode({"url": url, "timestamp": date.replace("-", "")})
    for attempt in range(3):
        try:
            req = urllib.request.Request("https://archive.org/wayback/available?" + q, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                snap = json.load(r).get("archived_snapshots", {}).get("closest")
            if snap and snap.get("available") and str(snap.get("status", "200")).startswith(("2", "3")):
                return snap["url"].replace("http://web.archive.org", "https://web.archive.org")
            return None
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None


def main():
    known = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    links = collect(known)
    todo = [u for u in links if u not in known or not known[u].get("archive")]
    print(f"{len(links)} outside links; checking {len(todo)}")
    today = datetime.date.today().isoformat()
    dead = {}
    with cf.ThreadPoolExecutor(24) as ex:
        for u, res in zip(todo, ex.map(check, todo)):
            if res in ("dns", "refused", "404", "410"):
                dead[u] = res
    print(f"{len(dead)} dead; looking up archive copies")
    for i, (u, res) in enumerate(sorted(dead.items())):
        arc = wayback(u, links[u])
        known[u] = {"archive": arc, "status": res, "checked": today}
        time.sleep(1)
        if i % 50 == 0:
            print(f"  {i}/{len(dead)}")
    # forget links no longer in any post
    known = {u: v for u, v in known.items() if u in links}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(known.items())), f, ensure_ascii=False, indent=1)
        f.write("\n")
    found = sum(1 for v in known.values() if v.get("archive"))
    print(f"Done: {len(known)} dead links, {found} with archive copies")


if __name__ == "__main__":
    sys.exit(main())
