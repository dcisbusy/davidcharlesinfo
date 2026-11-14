#!/usr/bin/env python3
"""
Builds davidcharles.info.

GitHub runs this every evening, and whenever home-intro.html, a post, or
anything in scripts/ or assets/ changes (see .github/workflows/build-site.yml).

What it does:
  1. Checks Substack for new newsletter issues  -> newsletter-archive/posts.json
  2. Rebuilds the homepage, the newsletter archive and the blog archive
  3. Re-wraps every old blog post and page in the site design. Each post keeps
     its own words between <!--content:start--> and <!--content:end-->; you can
     edit those on GitHub and the page is rebuilt around them.
  4. Rebuilds the category, tag and year pages, Random story, the 404 page and
     sitemap.xml

The list of blog posts and pages (titles, dates, categories, tags) lives in
blog-archive/index.json. The look of every page comes from assets/site.css.
"""

import html
import json
import os
import random
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SITE = "https://davidcharles.info"
SUBSTACK = "https://davidcharles.substack.com"
GOATCOUNTER = "davidcharles"    # GoatCounter site code (davidcharles.goatcounter.com). Set to "" to switch stats off.
CSS_VERSION = "8"               # Bump when assets/site.css or site.js changes, so browsers fetch the new one.

NEWSLETTER_DATA = "newsletter-archive/posts.json"
BLOG_DATA = "blog-archive/index.json"
INTRO = "home-intro.html"

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
TILE_COLOURS = ["#2f6b4f", "#4a7a8c", "#8a6d3b", "#5b6e3a", "#7a4e5c", "#3f5a7a", "#9a5b34", "#4f6f63"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

changed_files = []


# ---------------------------------------------------------------- helpers

def esc(s):
    return html.escape(s or "", quote=True)


def clean(text, limit=220):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:-") + "…"
    return text


def nice(d):
    try:
        y, m, day = d[:10].split("-")
        return f"{int(day)} {MONTHS[int(m) - 1]} {y}"
    except Exception:
        return d or ""


def file_for(url_path):
    return os.path.join(url_path.strip("/"), "index.html") if url_path.strip("/") else "index.html"


def read(path):
    return open(path, encoding="utf-8", errors="ignore").read() if os.path.exists(path) else None


def write_if_changed(path, text):
    if read(path) != text:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        changed_files.append(path)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------------------------------------------------------------- page template

NAV = [("/start-here/", "Start here"), ("/newsletter-archive/", "Newsletter"), ("/blog-archive/", "Archive"),
       ("/series/", "Series"), ("/map/", "Map"), ("/photos/", "Photos"), ("/search/", "Search")]


def page(title, description, path, body, current=None, image=None, kind="website", noindex=False):
    nav = "".join(
        f'<a href="{u}"{" aria-current=" + chr(34) + "page" + chr(34) if u == current else ""}>{esc(t)}</a>'
        for u, t in NAV)
    head = [
        '<!DOCTYPE html>',
        '<html lang="en-GB">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{esc(title)}</title>',
        f'<meta name="description" content="{esc(description)}">',
        f'<link rel="canonical" href="{SITE}{esc(path)}">',
        f'<link rel="stylesheet" href="/assets/site.css?v={CSS_VERSION}">',
        "<script>try{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t;}catch(e){}</script>",
        f'<link rel="alternate" type="application/rss+xml" title="David Charles" href="{SITE}/feed.xml">',
        f'<meta property="og:type" content="{kind}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{SITE}{esc(path)}">',
        '<meta property="og:site_name" content="David Charles">',
    ]
    if image:
        img = image if image.startswith("http") else SITE + image
        head += [f'<meta property="og:image" content="{esc(img)}">',
                 '<meta name="twitter:card" content="summary_large_image">']
    if noindex:
        head.append('<meta name="robots" content="noindex">')
    if GOATCOUNTER:
        head.append(f'<script data-goatcounter="https://{GOATCOUNTER}.goatcounter.com/count" async '
                    'src="//gc.zgo.at/count.js"></script>')
    return ("\n".join(head) + "\n</head>\n<body>\n<main>\n"
            f'<nav class="top"><a class="name" href="/">David Charles</a>{nav}'
            '<button class="theme-toggle" type="button">Dark</button></nav>\n'
            f"{body}\n</main>\n<script src=\"/assets/site.js?v={CSS_VERSION}\" defer></script>\n</body>\n</html>\n")


def redirect_page(to):
    return ('<!DOCTYPE html>\n<html lang="en-GB"><head><meta charset="utf-8"><title>Moved</title>'
            f'<link rel="canonical" href="{SITE if to.startswith("/") else ""}{esc(to)}">'
            f'<meta http-equiv="refresh" content="0; url={esc(to)}"></head>'
            f'<body><p><a href="{esc(to)}">This page has moved here.</a></p></body></html>\n')


SUBSCRIBE = f'<a class="button primary" href="{SUBSTACK}/subscribe">Subscribe on Substack</a>'
# The sign-up box at the end of posts. "Subscribe free" opens Substack's own sign-up form in place (site.js);
# nothing loads from Substack until someone taps it. The latest issue is filled in from /assets/latest.json.
SUBSCRIBE_BOX = (
    '<aside class="newsletter-box subscribe-box"><h2>Enjoyed this? There’s a new story every Friday.</h2>'
    '<p>These days I write a free weekly newsletter about adventure, nature and how to be human. '
    'Join the readers who get it in their inbox.</p>'
    '<p class="latest" hidden>Latest issue: <a href="/newsletter-archive/"></a></p>'
    f'<div class="buttons"><a class="button primary subscribe-open" href="{SUBSTACK}/subscribe?utm_source='
    'davidcharles.info&amp;utm_medium=archive&amp;utm_campaign=post-end">Subscribe free</a>'
    '<a class="button secondary" href="/newsletter-archive/">Read past issues</a></div>'
    '<div class="subscribe-embed"></div>'
    '<p class="small muted">Plus: <a href="/books/cycling-to-the-sahara/">Cycling to the Sahara</a>, a free ebook.</p>'
    '</aside>')


# ---------------------------------------------------------------- 1. newsletter

def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def from_api():
    posts, offset = [], 0
    while offset < 5000:
        batch = json.loads(get(f"{SUBSTACK}/api/v1/archive?sort=new&offset={offset}&limit=50"))
        if not isinstance(batch, list) or not batch:
            break
        for p in batch:
            if p.get("type") not in (None, "newsletter", "podcast"):
                continue
            title = (p.get("title") or "").strip()
            if title:
                posts.append({
                    "url": p.get("canonical_url") or f"{SUBSTACK}/p/{p.get('slug')}",
                    "title": title,
                    "date": (p.get("post_date") or "")[:10],
                    "excerpt": clean(p.get("subtitle") or p.get("description") or ""),
                    "image": p.get("cover_image") or "",
                    "paid": p.get("audience") == "only_paid",
                })
        if len(batch) < 50:
            break
        offset += 50
    return posts


def from_rss():
    root = ET.fromstring(get(f"{SUBSTACK}/feed"))
    posts = []
    for it in root.iter("item"):
        title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        try:
            date = parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
        except Exception:
            date = ""
        enc = it.find("enclosure")
        img = enc.get("url", "") if enc is not None and (enc.get("type") or "").startswith("image") else ""
        posts.append({"url": link, "title": title, "date": date,
                      "excerpt": clean(it.findtext("description")), "image": img, "paid": False})
    return posts


def from_relay():
    # Substack blocks requests from GitHub's servers, so a free feed-reading
    # service fetches the RSS for us. It only carries the latest ~10 issues.
    data = json.loads(get("https://api.rss2json.com/v1/api.json?rss_url=" + quote(f"{SUBSTACK}/feed", safe="")))
    if data.get("status") != "ok":
        raise RuntimeError(data.get("message") or "relay error")
    posts = []
    for it in data.get("items", []):
        title, link = (it.get("title") or "").strip(), (it.get("link") or "").strip()
        if not title or not link:
            continue
        enc = it.get("enclosure") or {}
        img = it.get("thumbnail") or (enc.get("link", "") if str(enc.get("type", "")).startswith("image") else "")
        posts.append({"url": link, "title": title, "date": (it.get("pubDate") or "")[:10],
                      "excerpt": clean(it.get("description")), "image": img, "paid": False})
    return posts


def update_newsletter(offline=False):
    key = lambda u: u.split("?")[0].split("#")[0].rstrip("/").lower()
    known = {}
    if os.path.exists(NEWSLETTER_DATA):
        for p in json.load(open(NEWSLETTER_DATA, encoding="utf-8")):
            known[key(p["url"])] = p
    fetched, errors = [], []
    if not offline:
        for source in (from_api, from_rss, from_relay):
            if source is from_relay and fetched:
                break
            try:
                got = source()
                print(f"{source.__name__}: {len(got)} issues")
                fetched += got
            except Exception as e:
                errors.append(f"{source.__name__}: {e}")
    if not fetched and not known:
        sys.exit("Could not read Substack: " + "; ".join(errors))
    for e in errors:
        print("Note:", e)
    # Only trust issues that really point at the Substack, with https images. This stops a
    # compromised feed relay from adding fake issues or javascript: links to the site.
    ok_url = lambda u: isinstance(u, str) and u.startswith(SUBSTACK + "/p/") and not re.search(r'[\s"<>]', u)
    ok_img = lambda u: isinstance(u, str) and u.startswith("https://") and not re.search(r'[\s"<>]', u)
    fetched = [dict(p, image=p.get("image") if ok_img(p.get("image")) else "", title=p["title"][:300],
                    excerpt=(p.get("excerpt") or "")[:1000], date=p.get("date", "")[:10])
               for p in fetched if ok_url(p.get("url"))]
    for p in fetched:
        merged = dict(known.get(key(p["url"]), {}))
        merged.update({k: v for k, v in p.items() if v or (k == "paid" and "paid" not in merged)})
        known[key(p["url"])] = merged
    issues = sorted(known.values(), key=lambda p: (p.get("date", ""), p["title"]), reverse=True)
    write_if_changed(NEWSLETTER_DATA, json.dumps(issues, ensure_ascii=False, indent=1))
    print(f"{len(issues)} newsletter issues")
    return issues


def issue_list(items, minutes=None):
    minutes = minutes or {}
    parts, year = [], None
    for p in items:
        y = (p.get("date") or "")[:4] or "Undated"
        if y != year:
            if year is not None:
                parts.append("</ol>")
            parts.append(f'<h2>{esc(y)}</h2>\n<ol class="issues">')
            year = y
        if p.get("image"):
            img = f'<img src="{esc(p["image"])}" alt="" loading="lazy" decoding="async" width="120" height="80">'
        else:
            colour = TILE_COLOURS[sum(map(ord, p["title"])) % len(TILE_COLOURS)]
            d = p.get("date") or ""
            day = str(int(d[8:10])) if len(d) >= 10 else ""
            mon = MONTHS[int(d[5:7]) - 1][:3] if len(d) >= 7 else ""
            img = (f'<span class="tile" style="background:{colour}" aria-hidden="true">'
                   f'<b>{esc(day)}</b><small>{esc(mon)}</small></span>')
        paid = ' <span class="paid">Paid</span>' if p.get("paid") else ""
        excerpt = f'<p>{esc(p["excerpt"])}</p>' if p.get("excerpt") else ""
        parts.append(
            f'<li><a href="{esc(p["url"])}">{img}<div>'
            f'<time datetime="{esc(p.get("date"))}">{esc(nice(p.get("date", "")))}'
            f'{" &middot; " + str(minutes[p["url"]]) + " min read" if p["url"] in minutes else ""}</time>'
            f'<h3>{esc(p["title"])}{paid}</h3>{excerpt}</div></a></li>')
    if year is not None:
        parts.append("</ol>")
    return "\n".join(parts)


# ---------------------------------------------------------------- 2. blog posts and pages

def post_rows(items):
    return '<ul class="posts">' + "".join(
        f'<li><time datetime="{esc(p["date"])}">{esc(nice(p["date"]))}</time>'
        f'<a href="{esc(p["url"])}">{esc(p["title"])}</a></li>' for p in items) + "</ul>"


def chips(items):
    return '<ul class="chips">' + "".join(
        f'<li><a href="{esc(u)}">{esc(n)} <span>{c}</span></a></li>' for u, n, c in items) + "</ul>"


CONTENT_RE = re.compile(r"<!--content:start-->(.*?)<!--content:end-->", re.S)

# Dead outside links found by scripts/linkcheck.py, with Internet Archive copies
try:
    DEAD = {u: v["archive"] for u, v in json.load(open("data/dead-links.json", encoding="utf-8")).items()
            if v.get("archive")}
except (OSError, ValueError):
    DEAD = {}


def archive_links(content):
    """Point dead links at their Wayback Machine copy: images use the raw-image form (im_), embedded
    players the frame form (if_), ordinary links the normal page. Safe to run again on its own output."""
    if not DEAD:
        return content

    def fix_tag(t):
        tag = t.group(1).lower()

        def fix(m):
            attr, url = m.group(1), m.group(2).replace("&amp;", "&")
            arc_m = re.match(r"https://web\.archive\.org/web/(\d+)(?:im_|if_)?/(https?://.+)$", url)
            orig = arc_m.group(2) if arc_m else url
            arc = DEAD.get(orig)
            if not arc:
                return m.group(0)
            if attr == "src":
                flag = "im_" if tag == "img" else "if_" if tag in ("iframe", "embed") else ""
                arc = re.sub(r"(/web/\d+)(?:im_|if_)?(/)", r"\1" + flag + r"\2", arc, count=1)
            return f'{attr}="{esc(arc)}"'
        return re.sub(r'\b(href|src)="(https?://[^"\s]+)"', fix, t.group(0))
    return re.sub(r"<(\w+)\b[^>]*>", fix_tag, content)


COMMENTS_RE = re.compile(r"<!--comments:start-->(.*?)<!--comments:end-->", re.S)


def wrap_entry(e, older, newer, extra=None):
    extra = extra or {}
    path = file_for(e["url"])
    s = read(path)
    if s is None:
        print("Missing file for", e["url"])
        return
    m = CONTENT_RE.search(s)
    if not m:
        print("No <!--content:start--> marker in", path, "- left as it is")
        return
    content = archive_links(m.group(1))
    c = COMMENTS_RE.search(s)
    comments = c.group(1) if c else ""

    words = len(re.findall(r"[A-Za-z\u00C0-\u024F'\u2019-]+", re.sub(r"<[^>]+>", " ", content)))
    minutes = max(1, round(words / 230))
    listen = ('<p class="listen" hidden><button class="listen-play" type="button">&#9654; Listen</button>'
              '<button class="listen-stop" type="button" hidden>&#9632; Stop</button></p>')
    meta = f'<p class="meta">{minutes} min read</p>' if e["type"] == "page" and words > 300 else ""
    if e["type"] == "post":
        cats = ", ".join(f'<a href="{esc(x["url"])}">{esc(x["name"])}</a>' for x in e.get("cats", []))
        meta = (f'<p class="meta"><time datetime="{esc(e["date"])}">{esc(nice(e["date"]))}</time>'
                + (f" &middot; {cats}" if cats else "") + f" &middot; {minutes} min read</p>")
    body = [f'<article class="entry">\n<header class="entry-head"><h1>{esc(e["title"])}</h1>{meta}'
            f'{listen if words > 150 else ""}</header>']
    if extra.get("newsletter"):
        body.append(f'<p class="first-appeared">This story first appeared in my newsletter. '
                    f'<a href="{esc(extra["newsletter"])}">Read it on Substack</a></p>')
    body.append(f'<div class="entry-content">\n<!--content:start-->{content}<!--content:end-->\n</div>')
    if extra.get("series"):
        body.append(extra["series"])
    if e["type"] == "post" or words > 300:
        body.append(SUBSCRIBE_BOX)
    if e["type"] == "post":
        if e.get("tags"):
            body.append('<p class="tags">Tagged: ' + ", ".join(
                f'<a href="{esc(t["url"])}">{esc(t["name"])}</a>' for t in e["tags"]) + "</p>")
        if extra.get("related"):
            body.append('<section class="related"><h2>Related reading</h2><ul class="posts">' + "".join(
                f'<li><time datetime="{esc(r["date"])}">{esc(nice(r["date"]))}</time><a href="{esc(r["url"])}">'
                f'{esc(r["title"])}</a>{" <span class=" + chr(34) + "via" + chr(34) + ">newsletter</span>" if r["source"] == "newsletter" else ""}</li>'
                for r in extra["related"]) + "</ul></section>")
    if comments.strip():
        n = len(re.findall(r'<li id="comment-', comments))
        body.append(f'<section class="comments"><h2 class="section">{n} comment{"s" if n != 1 else ""}</h2>\n'
                    f"<!--comments:start-->{comments}<!--comments:end-->\n</section>")
    if e["type"] == "post" and (older or newer):
        links = ""
        if older:
            links += f'<a class="prev" href="{esc(older["url"])}"><small>&larr; Older</small>{esc(older["title"])}</a>'
        else:
            links += "<span></span>"
        if newer:
            links += f'<a class="next" href="{esc(newer["url"])}"><small>Newer &rarr;</small>{esc(newer["title"])}</a>'
        body.append(f'<nav class="post-nav">{links}</nav>')
    body.append("</article>")
    description = e.get("excerpt") or e["title"]
    write_if_changed(path, page(f'{e["title"]} | David Charles', description, e["url"], "\n".join(body),
                                image=e.get("image"), kind="article" if e["type"] == "post" else "website"))


def build_blog(entries, ctx=None):
    per_post = (ctx or {}).get("per_post", {})
    posts = sorted([e for e in entries if e["type"] == "post"], key=lambda p: (p["date"], p["title"]))
    for i, e in enumerate(posts):
        wrap_entry(e, posts[i - 1] if i > 0 else None, posts[i + 1] if i + 1 < len(posts) else None,
                   per_post.get(e["url"]))
    for e in entries:
        if e["type"] == "page":
            wrap_entry(e, None, None)
    posts.reverse()                                   # newest first from here on
    years = sorted({p["date"][:4] for p in posts if p["date"]}, reverse=True)

    # Categories (including sub-categories)
    cats = {}
    for p in posts:
        for c in p.get("cats", []):
            cats.setdefault(c["url"], {"name": c["name"], "posts": []})["posts"].append(p)
    # A parent category also lists every post in its sub-categories (no duplicates, newest first)
    order = {id(p): i for i, p in enumerate(posts)}
    for u in sorted(cats, key=lambda u: -u.count("/")):
        seen = {id(p) for p in cats[u]["posts"]}
        for s2 in [s2 for s2 in cats if s2.startswith(u) and s2 != u]:
            for p in cats[s2]["posts"]:
                if id(p) not in seen:
                    seen.add(id(p)); cats[u]["posts"].append(p)
        cats[u]["posts"].sort(key=lambda p: order[id(p)])
    top_cats = sorted([u for u in cats if u.count("/") == 3], key=lambda u: (cats[u]["name"] == "Uncategorised",
                                                                              cats[u]["name"].lower()))
    for u, c in cats.items():
        subs = sorted([s for s in cats if s.startswith(u) and s != u and s.count("/") == u.count("/") + 1],
                      key=lambda s: cats[s]["name"].lower())
        parent = u.rsplit("/", 2)[0] + "/"
        crumbs = (f'<p class="meta crumbs"><a href="/blog-archive/">Blog archive</a>'
                  + (f' &rsaquo; <a href="{esc(parent)}">{esc(cats[parent]["name"])}</a>' if parent in cats else "")
                  + "</p>")
        body = (f'{crumbs}<h1>{esc(c["name"])}</h1>\n'
                f'<p class="intro muted">{len(c["posts"])} posts, newest first.</p>\n'
                + (chips([(s, cats[s]["name"], len(cats[s]["posts"])) for s in subs]) if subs else "")
                + "<h2>All posts</h2>\n" + post_rows(c["posts"]))
        write_if_changed(file_for(u), page(f'{c["name"]} | David Charles',
                                           f'{len(c["posts"])} posts from David Charles\'s blog about {c["name"]}.',
                                           u, body))

    # Tags
    tags = {}
    for p in posts:
        for t in p.get("tags", []):
            tags.setdefault(t["url"], {"name": t["name"], "posts": []})["posts"].append(p)
    for u, t in tags.items():
        n = len(t["posts"])
        body = (f'<p class="meta crumbs"><a href="/blog-archive/">Blog archive</a> &rsaquo; Tagged</p>'
                f'<h1>{esc(t["name"])}</h1>\n<p class="intro muted">{n} post{"s" if n != 1 else ""} tagged '
                f'&ldquo;{esc(t["name"])}&rdquo;.</p>\n' + post_rows(t["posts"]))
        write_if_changed(file_for(u), page(f'Posts tagged {t["name"]} | David Charles',
                                           f'Posts by David Charles tagged {t["name"]}.', u, body,
                                           noindex=n < 3))

    # Years
    year_chips = chips([(f"/{y}/", y, sum(1 for p in posts if p["date"].startswith(y))) for y in years])
    for y in years:
        ps = [p for p in posts if p["date"].startswith(y)]
        body = (f'<p class="meta crumbs"><a href="/blog-archive/">Blog archive</a></p><h1>{y}</h1>\n'
                f'<p class="intro muted">{len(ps)} posts from {y}.</p>\n{year_chips}\n<h2>All posts</h2>\n'
                + post_rows(ps))
        write_if_changed(file_for(f"/{y}/"), page(f"{y} | David Charles", f"Blog posts by David Charles from {y}.",
                                                  f"/{y}/", body))

    # Blog archive
    pages = sorted([e for e in entries if e["type"] == "page" and e.get("listed", True)],
                   key=lambda e: e["title"].lower())
    by_year = []
    for y in years:
        by_year.append(f'<h2 id="y{y}"><a href="/{y}/">{y}</a></h2>\n'
                       + post_rows([p for p in posts if p["date"].startswith(y)]))
    def kids(u):
        return sorted([s2 for s2 in cats if s2.startswith(u) and s2 != u and s2.count("/") == u.count("/") + 1],
                      key=lambda s2: cats[s2]["name"].lower())

    def branch(u):
        sub = kids(u)
        return (f'<li><a href="{esc(u)}">{esc(cats[u]["name"])} <span>{len(cats[u]["posts"])}</span></a>'
                + ('<ul>' + "".join(branch(k) for k in sub) + '</ul>' if sub else "") + "</li>")
    cat_tree = '<ul class="cat-tree">' + "".join(branch(u) for u in top_cats) + "</ul>"
    first, last = (years[-1], years[0]) if years else ("", "")
    body = (
        "<h1>Blog archive</h1>\n"
        f'<p class="intro muted">{len(posts)} posts written between {first} and {last}. For new writing, see the '
        '<a href="/newsletter-archive/">newsletter</a>. Or explore it on the <a href="/map/">map</a>, the '
        '<a href="/photos/">photo wall</a> or in <a href="/numbers/">20 years in numbers</a>, follow a '
        '<a href="/series/">series</a>, or try a <a href="/random-story/">random story</a>.</p>\n'
        '<h2 class="section">Pages</h2>\n<ul class="pages">'
        + "".join(f'<li><a href="{esc(e["url"])}">{esc(e["title"])}</a></li>' for e in pages) + "</ul>\n"
        '<h2 class="section">Categories</h2>\n' + cat_tree + "\n"
        '<h2 class="section">Years</h2>\n' + year_chips + "\n"
        '<h2 class="section">Every post</h2>\n' + "\n".join(by_year))
    write_if_changed("blog-archive/index.html",
                     page("Blog archive | David Charles", f"All {len(posts)} posts from David Charles's blog.",
                          "/blog-archive/", body, "/blog-archive/"))

    # The Random story page is the story picker, made in extras.build_picker
    return posts, pages, cats, years


# ---------------------------------------------------------------- 3. homepage, newsletter page, extras

def build_home(issues, posts, extra="", minutes=None):
    if not os.path.exists(INTRO):
        with open(INTRO, "w", encoding="utf-8") as f:
            f.write("<!-- Edit the words below. This becomes the top of the homepage. -->\n"
                    "<h1>Hello, I'm David Charles</h1>\n<p>Write something here.</p>\n")
    intro = re.sub(r"<!--.*?-->\s*", "", read(INTRO), flags=re.S).strip()
    body = (f'<div class="intro">\n{intro}\n</div>\n'
            f'<div class="buttons">{SUBSCRIBE}'
            '<a class="button secondary" href="/start-here/">Start here</a>'
            '<a class="button secondary" href="/search/">Search</a></div>\n'
            '<aside class="continue-home" hidden><h2 class="section">Carry on reading</h2><ul></ul></aside>\n'
            '<p class="quick-pick">Got <a href="/random-story/?m=2">2 minutes</a>, <a href="/random-story/?m=5">5</a>, '
            '<a href="/random-story/?m=10">10</a> or <a href="/random-story/?m=20">20</a>? '
            '<a href="/random-story/">Pick me a story</a></p>\n'
            '<p class="quick-pick">Explore: <a href="/timeline/">twenty-year timeline</a> &middot; '
            '<a href="/map/">map</a> &middot; <a href="/series/">series</a> &middot; <a href="/photos/">photo wall</a> '
            '&middot; <a href="/books/cycling-to-the-sahara/">free ebook</a></p>\n'
            + extra +
            '<h2 class="section" id="newsletter">The newsletter</h2>\n' + issue_list(issues, minutes))
    write_if_changed("index.html", page(
        "David Charles", "Writer and outdoor instructor. Read every issue of my newsletter, and the archive of my blog.",
        "/", body, "/"))
    body = ("<h1>Newsletter archive</h1>\n"
            '<p class="intro muted">Every issue of my newsletter, newest first. Click any issue to read it on '
            f'Substack.</p>\n<div class="buttons">{SUBSCRIBE}</div>\n' + issue_list(issues, minutes))
    write_if_changed("newsletter-archive/index.html", page(
        "Newsletter archive | David Charles",
        "Every issue of David Charles's newsletter, with links to read them on Substack.",
        "/newsletter-archive/", body, "/newsletter-archive/"))


def build_extras(posts, pages, cats, years):
    body = ('<h1>Page not found</h1>\n<p class="intro">Sorry, there\'s nothing at this address. '
            'It may have moved when this site stopped using WordPress.</p>\n'
            '<div class="buttons"><a class="button primary" href="/blog-archive/">Browse the blog archive</a>'
            '<a class="button secondary" href="/">Go to the homepage</a></div>')
    write_if_changed("404.html", page("Page not found | David Charles", "Page not found.", "/404.html", body,
                                      noindex=True))
    urls = [("/", ""), ("/start-here/", ""), ("/newsletter-archive/", ""), ("/blog-archive/", ""), ("/series/", ""),
            ("/map/", ""), ("/photos/", ""), ("/numbers/", ""), ("/search/", ""), ("/timeline/", ""),
            ("/random-story/", ""), ("/books/", "")]
    urls += [(u, "") for u in sorted("/" + os.path.dirname(f).replace(os.sep, "/") + "/"
                                     for f in __import__("glob").glob("series/*/index.html")
                                     + [f for f in __import__("glob").glob("books/*/index.html")
                                        if 'name="robots" content="noindex' not in (read(f) or "")])]
    if "noindex" not in (read("work-with-me/index.html") or "noindex"):
        urls.append(("/work-with-me/", ""))
    urls += [(p["url"], p["date"]) for p in posts] + [(p["url"], "") for p in pages]
    urls += [(u, "") for u in cats] + [(f"/{y}/", "") for y in years]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, d in urls:
        xml.append(f"<url><loc>{SITE}{esc(u)}</loc>" + (f"<lastmod>{d[:10]}</lastmod>" if d else "") + "</url>")
    xml.append("</urlset>")
    write_if_changed("sitemap.xml", "\n".join(xml) + "\n")
    exports = "".join(f"Disallow: /{d}/\n" for d in sorted(os.listdir(".")) if d.startswith("substackpostsexport"))
    write_if_changed("robots.txt", f"User-agent: *\nAllow: /\n{exports}Sitemap: {SITE}/sitemap.xml\n")


# ---------------------------------------------------------------- run

if __name__ == "__main__":
    offline = "--offline" in sys.argv          # skip Substack (for testing)
    issues = update_newsletter(offline)
    latest = next((i for i in sorted(issues, key=lambda i: i["date"], reverse=True) if not i.get("paid")), None)
    if latest:
        write_if_changed("assets/latest.json", json.dumps({"title": latest["title"], "url": latest["url"],
                                                            "date": latest["date"]}, ensure_ascii=False) + "\n")
    entries = json.load(open(BLOG_DATA, encoding="utf-8"))
    sys.modules["build"] = sys.modules[__name__]      # let extras.py share these helpers
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import extras
    ctx = extras.prepare(issues, entries)
    posts, pages, cats, years = build_blog(entries, ctx)
    home_extra = extras.build_pages(ctx, entries)
    build_home(issues, posts, home_extra, ctx["minutes"])
    build_extras(posts, pages, cats, years)
    print(f"{len(posts)} blog posts, {len(pages)} pages, {len(cats)} categories")
    print(f"{len(changed_files)} files updated")
    for f in changed_files[:20]:
        print("  ", f)
