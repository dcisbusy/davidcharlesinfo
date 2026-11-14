"""Tell search engines (Bing, Yandex, Seznam, Naver and others that share IndexNow) which pages just changed.

    python scripts/indexnow.py <old commit> <new commit>

Run by the Build site workflow after it pushes. Lists the changed pages between two commits and sends them to
api.indexnow.org. The key is the name of the <key>.txt file in the site root, which proves the site is ours.
Google does not use IndexNow; it reads sitemap.xml.
"""
import glob
import json
import os
import subprocess
import sys
import urllib.request

SITE_HOST = "davidcharles.info"
SKIP = ("pagefind/", "substackpostsexport", "assets/", "cards/", "work-with-me/")


def main(old, new):
    keys = [os.path.basename(f)[:-4] for f in glob.glob("*.txt") if len(os.path.basename(f)) == 36]
    if not keys:
        print("No IndexNow key file; skipping")
        return
    key = keys[0]
    files = subprocess.run(["git", "diff", "--name-only", old, new, "--", "*.html"], capture_output=True,
                           text=True).stdout.split()
    urls = []
    for f in files:
        if f.startswith(SKIP) or not f.endswith("index.html") or not os.path.exists(f):
            continue
        if 'name="robots" content="noindex' in open(f, encoding="utf-8", errors="ignore").read(4000):
            continue
        urls.append(f"https://{SITE_HOST}/" + f[:-len("index.html")])
    if not urls:
        print("No changed pages to report")
        return
    body = json.dumps({"host": SITE_HOST, "key": key, "keyLocation": f"https://{SITE_HOST}/{key}.txt",
                       "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"IndexNow: sent {len(urls)} pages, status {r.status}")
    except Exception as e:  # noqa: BLE001 - never fail the build over this
        print(f"IndexNow: not accepted ({e}); fine until the site is on HTTPS")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
