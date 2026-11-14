"""Turn a series into an ebook: EPUB (for phones, Kindle, Apple Books) and PDF (to read or print).

    python3 scripts/make_ebook.py cycling-to-the-sahara

Book details live in data/books.json. Needs pandoc and Google Chrome (for the PDF and the cover);
it runs on your own computer, not in the nightly build. Output goes to books/<slug>/ and is committed
like any other file. The build then makes the /books/ pages from data/books.json.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import build  # noqa: E402

sys.modules["build"] = build
import extras  # noqa: E402

SITE = build.SITE
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


def clean(content, stock):
    c = content
    c = re.sub(r"<span id=\"more-\d+\"></span>", "", c)
    # featured header images that are stock across the series
    c = re.sub(r'<figure class="featured">.*?</figure>', lambda m: "" if any(s in m.group(0) for s in stock)
               else m.group(0), c, flags=re.S)
    # old Blogger photo tables whose images were lost: drop tables with captions but no pictures
    c = re.sub(r"<table\b.*?</table>", lambda m: m.group(0) if "<img" in m.group(0) else "", c, flags=re.S)
    c = re.sub(r"<iframe\b.*?</iframe>", "", c, flags=re.S)
    c = re.sub(r"<script\b.*?</script>", "", c, flags=re.S)
    c = re.sub(r"<p>\s*(&nbsp;)?\s*</p>", "", c)
    # simple <img>: largest local version, no srcset
    def img(m):
        t = m.group(0)
        src = re.search(r'\ssrc="([^"]+)"', t)
        if not src:
            return ""
        s = src.group(1)
        full = re.sub(r"-\d+x\d+(?=\.\w+$)", "", s)
        if full.startswith("/") and os.path.exists(full.lstrip("/")):
            s = full
        if not s.startswith("/") or not os.path.exists(s.lstrip("/")):
            return ""                       # lost or remote image
        alt = re.search(r'\salt="([^"]*)"', t)
        return f'<img src="{os.path.abspath(s.lstrip("/"))}" alt="{alt.group(1) if alt else ""}">'
    c = re.sub(r"<img\b[^>]*>", img, c)
    c = re.sub(r'<figure\b[^>]*>', "<figure>", c)
    c = re.sub(r'<figcaption\b[^>]*>', "<figcaption>", c)
    c = re.sub(r"<figure>\s*</figure>", "", c)
    c = re.sub(r"<figure>\s*<figcaption>.*?</figcaption>\s*</figure>", "", c, flags=re.S)
    # site-relative links become full links
    c = re.sub(r'href="/', f'href="{SITE}/', c)
    c = re.sub(r'\s(class|id|style|width|height|sizes|srcset|loading|decoding|aria-describedby)="[^"]*"', "", c)
    return c.strip()


def main(slug):
    books = json.load(open("data/books.json", encoding="utf-8"))["books"]
    book = next(b for b in books if b["slug"] == slug)
    issues = json.load(open("newsletter-archive/posts.json", encoding="utf-8"))
    entries = json.load(open("blog-archive/index.json", encoding="utf-8"))
    stories, _ = extras.load_stories(issues, entries)
    sr = next(s for s in extras.build_series_data(stories, entries) if s["slug"] == book["series"])
    stock = book.get("skip_images", [])

    chapters = []
    for it in sr["items"]:
        path = build.file_for(it["blog_url"] or it["url"])
        m = build.CONTENT_RE.search(open(path, encoding="utf-8").read())
        title = re.sub(book["strip_prefix"], "", it["title"]) if book.get("strip_prefix") else it["title"]
        chapters.append((dict(it, title=title), clean(m.group(1), stock)))

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
        subprocess.run(["convert", f"{tmp}/cover.png", "-quality", "86", f"{out}/cover.jpg"], check=True)
    subprocess.run(["convert", f"{out}/cover.jpg", "-resize", "600x900", "-quality", "82",
                    f"{out}/cover-small.jpg"], check=True)

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
    epub_src = (f'<section class="intro"><h1>Before you set off</h1>{intro}</section>\n'
                + body + f'<section><h1>After the ride</h1>{end}</section>')
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
<section class="front"><h1>Before you set off</h1>{intro}</section>
<section class="front toc"><h1>Contents</h1><ol>{toc}</ol></section>
{body}
<section class="back"><h1>After the ride</h1>{end}</section>
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
    print(f"{len(chapters)} chapters, {words:,} words")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "cycling-to-the-sahara")
