"""Turn a series into an ebook: EPUB (for phones, Kindle, Apple Books) and PDF (to read or print).

    python3 scripts/make_ebook.py cycling-to-the-sahara

Book details live in data/books.json. Needs pandoc and Google Chrome (for the PDF and the cover);
it runs on your own computer, not in the nightly build. Output goes to books/<slug>/ and is committed
like any other file. The build then makes the /books/ pages from data/books.json.
"""
import html
import html.entities
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
import build  # noqa: E402

sys.modules["build"] = build
import extras  # noqa: E402
import lock  # noqa: E402

SITE = build.SITE
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


IMG_CACHE = os.path.join(tempfile.gettempdir(), "ebook-images")


def fetch_image(url):
    """Download a newsletter image once and shrink it for the book. Returns a local path or None."""
    import hashlib
    import urllib.request
    os.makedirs(IMG_CACHE, exist_ok=True)
    url = html.unescape(url)
    # Substack's CDN wraps the original: ask it for a 1400px JPEG
    m = re.search(r"/(https?%3A%2F%2F[^?\s]+)$", url)
    original = urllib.parse.unquote(m.group(1)) if m else url
    path = os.path.join(IMG_CACHE, hashlib.sha1(original.encode()).hexdigest() + ".jpg")
    if os.path.exists(path):
        return path
    for u in (f"https://substackcdn.com/image/fetch/w_1400,c_limit,f_jpg,q_80/{urllib.parse.quote(original, safe='')}",
              original):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (davidcharles.info ebook maker)"})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((1400, 1400))
            im.save(path, "JPEG", quality=80, optimize=True, progressive=True)
            return path
        except Exception as e:  # noqa: BLE001
            last = e
    print(f"  could not fetch image {original[:90]}: {last}")
    return None


def cut_sections(c, pattern):
    """Remove whole sections whose heading matches pattern (up to the next heading that doesn't).
    Numbered sub-headings ('1. …') belong to whichever section they sit in."""
    if not pattern:
        return c
    parts = re.split(r"(<h[1-4]\b[^>]*>.*?</h[1-4]>)", c, flags=re.S)
    out, cutting = [], False
    for part in parts:
        hm = re.match(r"<h[1-4]\b[^>]*>(.*?)</h[1-4]>", part, re.S)
        if hm:
            text = html.unescape(re.sub(r"<[^>]+>", "", hm.group(1))).strip()
            if re.match(r"\d+\.\s", text):
                pass                                    # keep current state
            else:
                cutting = bool(re.search(pattern, text, re.I))
        if not cutting:
            out.append(part)
    return "".join(out)


LOCAL_COPY = re.compile(r"(?:davidcharles\.info|cyclingtosyria\.com)/(wp-content/uploads/[^?\s]+?)(?:\?|$)")
BLOCK = re.compile(r"(<h[3-6]\b.*?</h[3-6]>|<p\b.*?</p>|<figure\b.*?</figure>|<blockquote\b.*?</blockquote>|<ul\b.*?</ul>|"
                   r"<ol\b.*?</ol>|<img\b[^>]*>|<hr\s*/?>|<table\b.*?</table>|<pre\b.*?</pre>|<h4\b.*?</h4>)", re.S)


def img_key(src):
    return os.path.basename(html.unescape(src).split("?")[0])[:80]


def plain(h):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", h)).split())


def phrase_pattern(phrase):
    """A plain-text phrase as a regex over HTML: characters may be entities, tags may sit between words."""
    def ch(c):
        if c.isalnum():
            return re.escape(c)
        alts = [re.escape(c), f"&#{ord(c)};", f"&#x{ord(c):x};"]
        if ord(c) in html.entities.codepoint2name:
            alts.append(f"&{html.entities.codepoint2name[ord(c)]};")
        return "(?:" + "|".join(alts) + ")"
    gap = r"(?:\s|&nbsp;|&#160;|\xa0|<[^>]+>)+"
    return gap.join("".join(ch(c) for c in w) + r"(?:<[^>]+>)*" for w in phrase.split())


def apply_edits(body, edit):
    """Cut the paragraphs and phrases listed for this chapter in data/book-edits.json."""
    cuts = [c["text"] for c in edit.get("cut", []) if c.get("text")]   # whole text, or its first 70 characters
    parts = BLOCK.split(body)
    body = "".join(p for p in parts if not (BLOCK.fullmatch(p.strip() or "x") and plain(p)
                                            and any(plain(p) == c or (len(c) >= 70 and plain(p).startswith(c))
                                                    for c in cuts)))
    for phrase in edit.get("cut_text", []):
        new = re.sub(r"\s?" + phrase_pattern(phrase), "", body, count=1)
        if new == body:
            print(f"  edit not found: {phrase[:60]}")
        body = new
    for r in edit.get("replace", []):           # David's own rewording of a phrase
        new = re.sub(phrase_pattern(r["from"]), lambda m: html.escape(r["to"], quote=False), body, count=1)
        if new == body:
            print(f"  edit not found: {r['from'][:60]}")
        body = new
    body = re.sub(r"<p>\s*</p>", "", body)
    return body


def clean(content, stock, book, cut_imgs=frozenset()):
    c = content
    c = re.sub(r"<span id=\"more-\d+\"></span>", "", c)
    # Substack furniture: buttons, icons, sign-up and share widgets, embeds
    for tag in ("button", "svg", "script", "style", "iframe", "form", "noscript"):
        c = re.sub(rf"<{tag}\b.*?</{tag}>", "", c, flags=re.S | re.I)
    c = re.sub(r'<div class="[^"]*(subscription-widget|subscribe-widget|embedded-post|youtube-wrap|tweet|'
               r'digest-post-embed|install-substack|captioned-button|poll-embed|image-link-expand)[^"]*".*?</div>\s*</div>',
               "", c, flags=re.S)
    c = re.sub(r'<p class="button-wrapper".*?</p>', "", c, flags=re.S)
    c = re.sub(r"<source\b[^>]*>", "", c)
    c = re.sub(r"</?picture\b[^>]*>", "", c)
    c = cut_sections(c, book.get("cut_headings"))
    for pat in book.get("cut_paragraphs", []):
        c = re.sub(r"<p\b[^>]*>(?:(?!</p>).)*?" + pat + r".*?</p>", "", c, flags=re.S | re.I)
    # featured header images that are stock across the series
    c = re.sub(r'<figure class="featured">.*?</figure>', lambda m: "" if any(s in m.group(0) for s in stock)
               else m.group(0), c, flags=re.S)
    # old Blogger photo tables whose images were lost: drop tables with captions but no pictures
    c = re.sub(r"<table\b.*?</table>", lambda m: m.group(0) if "<img" in m.group(0) else "", c, flags=re.S)
    c = re.sub(r"<p>\s*(&nbsp;)?\s*</p>", "", c)

    def img(m):
        t = m.group(0)
        src = re.search(r'\ssrc="([^"]+)"', t)
        if not src:
            return ""
        s = src.group(1)
        alt = re.search(r'\salt="([^"]*)"', t)
        alt = alt.group(1) if alt else ""
        if any(w in s for w in stock):
            return ""
        if img_key(s) in cut_imgs:
            return ""                       # a photo cut in data/book-edits.json
        lm = LOCAL_COPY.search(s)           # an old WordPress photo we still have on disk
        if lm and os.path.exists(re.sub(r"-\d+x\d+(?=\.\w+$)", "", lm.group(1))):
            s = "/" + re.sub(r"-\d+x\d+(?=\.\w+$)", "", lm.group(1))
        if s.startswith(("http://", "https://")):
            local = fetch_image(s)
            return f'<img src="{local}" alt="{alt}">' if local else ""
        full = re.sub(r"-\d+x\d+(?=\.\w+$)", "", s)
        if full.startswith("/") and os.path.exists(full.lstrip("/")):
            s = full
        if not s.startswith("/") or not os.path.exists(s.lstrip("/")):
            return ""                       # lost image
        if img_key(s) in cut_imgs:
            return ""
        return f'<img src="{os.path.abspath(s.lstrip("/"))}" alt="{alt}">'
    c = re.sub(r"<img\b[^>]*>", img, c)
    # unwrap image links
    c = re.sub(r'<a\b[^>]*>\s*(<img\b[^>]*>)\s*</a>', r"\1", c, flags=re.S)
    c = re.sub(r"<div\b[^>]*>", "", c)
    c = re.sub(r"</div>", "", c)
    # a link left holding nothing (its photo was cut or lost), so its caption doesn't stand alone below
    c = re.sub(r"<a\b[^>]*>\s*</a>", "", c)
    c = re.sub(r'<figure\b[^>]*>', "<figure>", c)
    c = re.sub(r'<figcaption\b[^>]*>', "<figcaption>", c)
    c = re.sub(r"<figure>\s*</figure>", "", c)
    c = re.sub(r"<figure>\s*<figcaption>.*?</figcaption>\s*</figure>", "", c, flags=re.S)
    # a photo cut or lost: its caption goes too ("Not these", "Photo of … by …")
    c = re.sub(r"<figure>(?:(?!</figure>).)*</figure>", lambda m: m.group(0) if "<img" in m.group(0) else "", c, flags=re.S)
    # newsletter greetings that headed the issue, not the story
    c = re.sub(r"<h[1-6]\b[^>]*>\s*(?:<strong>)?\s*Happy Friday!?\s*(?:</strong>)?\s*</h[1-6]>", "", c, flags=re.I)
    # chapter sub-headings sit below the chapter title
    c = re.sub(r"<(/?)h[1-2]\b", r"<\1h3", c)
    # site-relative links become full links
    c = re.sub(r'href="/', f'href="{SITE}/', c)
    c = re.sub(r'\s(class|id|style|width|height|sizes|srcset|loading|decoding|aria-describedby|data-[\w-]+|'
               r'target|rel|tabindex|role|aria-[\w-]+)="[^"]*"', "", c)
    c = re.sub(r"<p>\s*(&nbsp;|<br\s*/?>)?\s*</p>", "", c)
    # headings left with nothing under them (their links or buttons were Substack furniture)
    c = re.sub(r"<h([3-6])>(?:(?!</h\1>).)*</h\1>\s*(?=<h[1-6]\b|<figure>\s*<img|$)", "", c, flags=re.S)
    c = re.sub(r">([^<]+)<", lambda m: ">" + break_long(m.group(1)) + "<", ">" + c + "<")[1:-1]
    return c.strip()


def break_long(text):
    """Let very long run-together words ("Sorrytobotheryou…") break at the end of a line, so a justified line
    above them isn't stretched wide."""
    return re.sub(r"[^\s<>&;/]{26,}", lambda m: "\u200b".join(m.group(0)[i:i + 12] for i in range(0, len(m.group(0)), 12)), text)


def drop_title_heading(body, titles):
    """A heading near the start that only repeats the chapter's title (or just says "Thighs of Steel"):
    the newsletter's section heading, left over from cutting the issue down to this story."""
    def norm(t):
        return re.sub(r"[^a-z0-9]", "", html.unescape(re.sub(r"<[^>]+>", "", t)).lower())
    wanted = {norm(t) for t in titles if t}
    for m in list(re.finditer(r"<h[3-6]>(.*?)</h[3-6]>", body, re.S))[:3]:
        before = re.sub(r"<figure>.*?</figure>|<hr\s*/?>", "", body[:m.start()], flags=re.S).strip()
        h = norm(m.group(1))
        if h in wanted or (h == "thighsofsteel" and not before):
            return body[:m.start()] + body[m.end():]
    return body


def chapter_source(it, st):
    """A chapter's HTML: the newsletter issue, unless the blog post is the fuller telling. Some 2016 issues
    were only a teaser ('a short video…') for a blog post; the blog post is the story."""
    def words(h):
        return len(re.sub(r"<[^>]+>", " ", h or "").split())
    blog = None
    if it.get("blog_url") or not (st and st.get("html")):
        try:
            m = build.CONTENT_RE.search(open(build.file_for(it.get("blog_url") or it["url"]), encoding="utf-8").read())
            blog = m.group(1) if m else None
        except OSError:
            blog = None
    news = st.get("html") if st else None
    if news and (not blog or words(news) >= 0.6 * words(blog)):
        return news
    return blog or news or ""


def main(slug):
    lock.content_key(create=False)   # fail now, not after the build, if SUBSCRIBER_PASSWORD is missing or wrong
    books = json.load(open("data/books.json", encoding="utf-8"))["books"]
    book = next(b for b in books if b["slug"] == slug)
    issues = json.load(open("newsletter-archive/posts.json", encoding="utf-8"))
    entries = json.load(open("blog-archive/index.json", encoding="utf-8"))
    stories, _ = extras.load_stories(issues, entries)
    sr = next(s for s in extras.build_series_data(stories, entries) if s["slug"] == book["series"])
    stock = book.get("skip_images", [])
    by_url = {s["url"]: s for s in stories}
    skip = set(book.get("skip_chapters", []))
    # chapter-by-chapter edits (cut paragraphs, phrases, photos, whole chapters), applied once approved
    try:
        ed = json.load(open("data/book-edits.json", encoding="utf-8")).get(slug, {})
    except OSError:
        ed = {}
    edits = ed.get("chapters", {}) if ed.get("approved") else {}

    chapters = []
    years = book.get("years")   # e.g. [2018, 2023]: only chapters from those years
    for it in sr["items"]:
        if it["url"] in skip or it.get("blog_url") in skip:
            continue
        if years and not years[0] <= int(it["date"][:4]) <= years[1]:
            continue
        edit = edits.get(it["url"], {})
        if edit.get("drop"):
            continue
        content = chapter_source(it, by_url.get(it["url"]))
        title = re.sub(book["strip_prefix"], "", it["title"]) if book.get("strip_prefix") else it["title"]
        title = re.sub(r"^#\d+:?\s*", "", title)
        body = clean(content, stock, book, {c["img"] for c in edit.get("cut", []) if c.get("img")})
        # newsletter issues repeat their own title as the first heading
        body = re.sub(r"^\s*<h3>\s*(?:<strong>)?" + re.escape(html.escape(it["title"], quote=False)) + r"(?:</strong>)?\s*</h3>",
                      "", body)
        body = re.sub(r"^\s*<h3>\s*" + re.escape(it["title"]) + r"\s*</h3>", "", body)
        if edit:
            body = apply_edits(body, edit)
        body = drop_title_heading(body, [title, it["title"], edit.get("title") or ""])
        # a footnote number whose note was cut with the rest of the issue, and dividers left at the end
        body = re.sub(r'<a href="#footnote-anchor-\d+"[^>]*>\d+</a>\s*(?=$|<hr|<h\d)', "", body.strip())
        body = re.sub(r"(?:\s*<hr\s*/?>)+\s*$", "", body)
        chapters.append((dict(it, title=edit.get("title") or title), body))

    out = f"books/{slug}"
    os.makedirs(out, exist_ok=True)
    cover = os.path.abspath(book["cover_photo"].lstrip("/"))
    year = sr["items"][0]["date"][:4]

    # ---- cover (1600 x 2263, the shape of an A5 page) drawn with Chrome
    cover_html = f"""<!doctype html><meta charset="utf-8"><style>
    @page {{ margin: 0 }} html,body {{ margin:0; width:1600px; height:2263px; background:#f3ead8; }}
    body {{ font-family: Lora, Georgia, serif; color:#2a1f14; display:flex; flex-direction:column; }}
    .top {{ padding: 170px 120px 60px; }}
    .kicker {{ font: 600 44px/1 Inter, sans-serif; letter-spacing: .18em; text-transform: uppercase; color:#b4562b; }}
    h1 {{ font-size: 210px; line-height: .95; margin: 40px 0 0; font-weight: 700; letter-spacing: -.02em; }}
    .sub {{ font-size: 60px; line-height: 1.25; margin-top: 50px; font-style: italic; color:#5a4632; }}
    .photo {{ flex: 1; margin: 30px 0 0; background: url('file://{cover}') center/cover; }}
    .by {{ background:#2a1f14; color:#f3ead8; padding: 70px 120px; font: 600 72px/1 Inter, sans-serif;
          letter-spacing: .04em; }}
    </style><div class="top"><div class="kicker">{html.escape(book.get("kicker", year))}</div>
    <h1>{html.escape(book["title"])}</h1><div class="sub">{html.escape(book["subtitle"])}</div></div>
    <div class="photo"></div><div class="by">David Charles</div>"""
    with tempfile.TemporaryDirectory() as tmp:
        hp = os.path.join(tmp, "cover.html")
        open(hp, "w", encoding="utf-8").write(cover_html)
        subprocess.run([CHROME, "--headless", "--no-sandbox", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--allow-file-access-from-files", "--window-size=1600,2263",
                        f"--screenshot={tmp}/cover.png", "file://" + hp], check=True, capture_output=True)
        from PIL import Image
        im = Image.open(f"{tmp}/cover.png").convert("RGB")
        im.save(f"{out}/cover.jpg", "JPEG", quality=86, optimize=True)
        im.thumbnail((600, 900))
        im.save(f"{out}/cover-small.jpg", "JPEG", quality=82, optimize=True)

    # ---- the book as one HTML document
    intro = book["intro_html"]
    toc = "".join(f'<li><a href="#ch{i + 1}">{html.escape(it["title"])}</a></li>'
                  for i, (it, _) in enumerate(chapters))
    body = "".join(
        f'<section class="chapter" id="ch{i + 1}"><h1>{html.escape(it["title"])}</h1>'
        f'<p class="date">{html.escape(build.nice(it["date"]))}</p>{c}</section>\n'
        for i, (it, c) in enumerate(chapters))
    end = book["end_html"].replace("{SITE}", SITE)
    words = sum(len(re.sub(r"<[^>]+>", " ", c).split()) for _, c in chapters)

    # EPUB via pandoc (one chapter per <h1>)
    # pandoc only splits chapters at top-level headings, so no <section> wrappers in the EPUB source
    epub_body = "".join(
        f'<h1 id="ch{i + 1}">{html.escape(it["title"])}</h1>\n<p class="date">{html.escape(build.nice(it["date"]))}</p>\n{c}\n'
        for i, (it, c) in enumerate(chapters))
    epub_src = (f'<h1>{book.get("intro_title", "Before you set off")}</h1>\n{intro}\n'
                + epub_body + f'<h1>{book.get("end_title", "After the ride")}</h1>\n{end}')
    meta = os.path.join(out, ".meta.yaml")
    open(meta, "w", encoding="utf-8").write(
        f'---\ntitle: "{book["title"]}"\nsubtitle: "{book["subtitle"]}"\ncreator:\n  - role: author\n'
        f'    text: David Charles\nlang: en-GB\ndate: "{year}"\nrights: "{book["rights"]}"\n'
        f'publisher: davidcharles.info\n---\n')
    css = os.path.join(out, ".epub.css")
    open(css, "w").write("body{font-family:serif;line-height:1.5} h1{font-size:1.5em;margin:1.5em 0 .2em;"
                         "line-height:1.2} .date{color:#777;font-style:italic;margin-top:0} img{max-width:100%;"
                         "height:auto;display:block;margin:1em auto} figure{margin:1em 0} figcaption{font-size:.85em;"
                         "color:#666;text-align:center;font-style:italic} blockquote{margin:1em 1.5em;font-style:italic}")
    src = os.path.join(out, ".book.html")
    open(src, "w", encoding="utf-8").write(f"<html><body>{epub_src}</body></html>")
    subprocess.run(["pandoc", src, f"--metadata-file={meta}", "-f", "html", "-o", f"{out}/{slug}.epub", "--toc", "--toc-depth=1",
                    "--split-level=1", f"--epub-cover-image={out}/cover.jpg", f"--css={css}",
                    "--resource-path=."], check=True)

    # PDF via Chrome: A5 pages, cover first
    pdf_html = f"""<!doctype html><html lang="en-GB"><meta charset="utf-8"><title>{html.escape(book["title"])}</title>
<style>
@page {{ size: A5; margin: 18mm 16mm 20mm; }}
html, body {{ margin: 0; }}
body {{ font: 10.5pt/1.55 Lora, Georgia, serif; color: #1d1a16; }}
h1 {{ font-size: 20pt; line-height: 1.15; margin: 0 0 4pt; page-break-after: avoid; }}
.chapter, .front, .back {{ page-break-before: always; }}
.date {{ color: #8a7a68; font-style: italic; margin: 0 0 14pt; }}
p {{ margin: 0 0 7pt; text-align: justify; hyphens: auto; orphans: 2; widows: 2; }}
img {{ max-width: 100%; max-height: 120mm; display: block; margin: 8pt auto; page-break-inside: avoid; }}
figure {{ margin: 10pt 0; page-break-inside: avoid; }} figcaption {{ font-size: 8.5pt; color: #6d6052;
  text-align: center; font-style: italic; }}
a {{ color: inherit; text-decoration: none; }}
.toc ol {{ padding-left: 18pt; }} .toc li {{ margin: 0 0 3pt; }}
.title-page {{ text-align: center; padding-top: 50mm; }}
.title-page h1 {{ font-size: 28pt; }} .title-page p {{ text-align: center; }}
</style>
<div class="title-page"><h1>{html.escape(book["title"])}</h1><p><em>{html.escape(book["subtitle"])}</em></p>
<p style="margin-top:30mm">David Charles</p><p style="font-size:8.5pt;color:#8a7a68;margin-top:40mm">
{html.escape(book["rights"])}<br>{SITE.replace("https://", "")}</p></div>
<section class="front"><h1>{book.get("intro_title", "Before you set off")}</h1>{intro}</section>
<section class="front toc"><h1>Contents</h1><ol>{toc}</ol></section>
{body}
<section class="back"><h1>{book.get("end_title", "After the ride")}</h1>{end}</section>
</html>"""
    ph = os.path.abspath(f"{out}/.print.html")
    open(ph, "w", encoding="utf-8").write(pdf_html)
    cp = os.path.abspath(f"{out}/.cover-print.html")
    open(cp, "w").write(f'<!doctype html><style>@page{{size:A5;margin:0}}html,body{{margin:0}}img{{width:148mm;'
                        f'height:209.5mm;display:block;object-fit:cover}}</style>'
                        f'<img src="file://{os.path.abspath(out)}/cover.jpg">')
    for page_file, pdf in ((cp, ".cover.pdf"), (ph, ".inside.pdf")):
        subprocess.run([CHROME, "--headless", "--no-sandbox", "--allow-file-access-from-files",
                        "--no-pdf-header-footer", f"--print-to-pdf={os.path.abspath(out)}/{pdf}",
                        "file://" + page_file], check=True, capture_output=True)
    subprocess.run(["pdfunite", f"{out}/.cover.pdf", f"{out}/.inside.pdf", f"{out}/{slug}.pdf"], check=True)
    for f in (meta, css, src, ph, cp, f"{out}/.cover.pdf", f"{out}/.inside.pdf"):
        os.remove(f)
    for f in (f"{slug}.epub", f"{slug}.pdf"):
        print(f"{out}/{f}: {os.path.getsize(f'{out}/{f}') // 1024} KB")
        lock.lock_file(f"{out}/{f}", f"{out}/{f}.locked")   # subscribers only: keep just the locked copy
    print(f"{len(chapters)} chapters, {words:,} words")
    with open(f"{out}/stats.json", "w", encoding="utf-8") as f:   # the book page shows these
        json.dump({"chapters": len(chapters), "words": words}, f)
        f.write("\n")
    return words


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "cycling-to-the-sahara")
