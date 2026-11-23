"""Make a paid subscribers' ebook (EPUB and PDF) from David's own finished manuscript, and lock it.

    PAID_SUBSCRIBER_PASSWORD='…' python3 scripts/make_paid_book.py <slug> <manuscript.odt|.docx|.epub|.md>

The book's details are in data/books.json under "paid_books" (title, subtitle, cover, rights). The manuscript
is the book exactly as published: nothing is cut or rewritten. It is NOT kept in this repository (the repo is
public); only the locked copies are written, to books/<slug>/<slug>.epub.locked and .pdf.locked, plus the
cover and stats.json. Needs pandoc, Google Chrome, pdfunite (poppler) and Pillow, and the Lora font for the PDF.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lock  # noqa: E402

CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


def main(slug, manuscript):
    lock.content_key(create=False, tier="paid")   # fail now if PAID_SUBSCRIBER_PASSWORD is missing or wrong
    book = next(b for b in json.load(open("data/books.json", encoding="utf-8"))["paid_books"] if b["slug"] == slug)
    out = f"books/{slug}"
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp()

    # Cover: the book's own cover, saved at full size and as a small card
    from PIL import Image
    im = Image.open(book["cover_source"]).convert("RGB")
    im.save(f"{out}/cover.jpg", quality=88)
    small = im.copy()
    small.thumbnail((600, 900))
    small.save(f"{out}/cover-small.jpg", quality=85)

    # The manuscript as Markdown. Word/ODT "quotation" styles in the front matter (copyright page, dedication)
    # come through as block quotes; show those as plain paragraphs.
    md = subprocess.run(["pandoc", manuscript, "-t", "markdown", f"--extract-media={tmp}/media"],
                        check=True, capture_output=True, text=True).stdout
    first = md.find("\n# ")
    if first > 0:
        md = re.sub(r"(?m)^> ?", "", md[:first]) + md[first:]
    words = len(re.findall(r"[A-Za-z][A-Za-z'’-]*", re.sub(r"[#*\\>_-]", " ", md)))
    chapters = len(re.findall(r"(?m)^## ", md)) or len(re.findall(r"(?m)^# ", md))
    open(f"{tmp}/book.md", "w", encoding="utf-8").write(md)
    body = subprocess.run(["pandoc", f"{tmp}/book.md", "-t", "html5"], check=True, capture_output=True, text=True).stdout
    # Front matter (before the first part): one page each, starting at the paragraphs named in "front_pages";
    # "front_centre" and "front_small" are the numbers of the pages (0 = title page) to centre or set small.
    cut = body.find("<h1")
    front, rest = (body[:cut], body[cut:]) if cut > 0 else ("", body)
    if front and book.get("front_pages"):
        starts = sorted({m.start() for t in book["front_pages"]
                         for m in [re.search(r"<p>(?:<[^>]+>)*" + re.escape(html.escape(t, quote=False))[:60], front)] if m})
        parts = [front[a:b] for a, b in zip([0] + starts, starts + [len(front)])]
        front = "".join(
            f'<section class="front{" centre" if i in book.get("front_centre", [0]) else ""}'
            f'{" small" if i in book.get("front_small", []) else ""}{" first" if i == 0 else ""}">{p}</section>'
            for i, p in enumerate(parts))
    body = front + rest
    src = f"{tmp}/book.html"
    open(src, "w", encoding="utf-8").write(f"<html><body>{body}</body></html>")

    meta = f"{tmp}/meta.yaml"
    open(meta, "w", encoding="utf-8").write(
        f'---\ntitle: "{book["title"]}"\nsubtitle: "{book["subtitle"]}"\ncreator:\n  - role: author\n'
        f'    text: David Charles\nlang: en-GB\ndate: "{book.get("year", "")}"\nrights: "{book["rights"]}"\n---\n')
    css = f"{tmp}/epub.css"
    open(css, "w").write("body{font-family:serif;line-height:1.5} h1{font-size:1.6em;margin:1.5em 0 .2em;line-height:1.2}"
                         " h2{font-size:1.25em;margin:1.4em 0 .4em} h3{font-size:1em;font-weight:normal;font-style:italic;"
                         "color:#777;margin:0 0 1em} img{max-width:100%;height:auto;display:block;margin:1em auto}"
                         " blockquote{margin:1em 1.5em;font-style:italic} section.front{page-break-before:always}"
                         " section.first{page-break-before:auto} .centre{text-align:center;margin-top:3em} .centre p{text-align:center}"
                         " .small p{font-size:.8em;margin:0 0 .6em}")
    subprocess.run(["pandoc", src, "-f", "html", f"--metadata-file={meta}", "-o", f"{tmp}/{slug}.epub", "--toc", "--toc-depth=2",
                    "--split-level=2", f"--epub-cover-image={out}/cover.jpg", f"--css={css}",
                    f"--resource-path={tmp}"], check=True)

    # PDF via Chrome: A5 pages, cover first, each part on a new page
    page = f"""<!doctype html><html lang="en-GB"><meta charset="utf-8"><title>{html.escape(book["title"])}</title>
<style>
{__import__("make_ebook").lora_css()}
@page {{ size: A5; margin: 18mm 16mm 20mm; }}
html, body {{ margin: 0; }}
body {{ font: 10.5pt/1.55 Lora, Georgia, serif; color: #1d1a16; }}
h1 {{ font-size: 20pt; line-height: 1.15; margin: 0 0 4pt; page-break-before: always; page-break-after: avoid; }}
h2 {{ font-size: 13pt; margin: 18pt 0 6pt; page-break-after: avoid; }}
h3 {{ font-size: 10.5pt; font-weight: normal; font-style: italic; color: #8a7a68; margin: 0 0 14pt; }}
p {{ margin: 0 0 7pt; text-align: justify; hyphens: auto; orphans: 2; widows: 2; }}
blockquote {{ margin: 8pt 14pt; font-style: italic; }}
img {{ max-width: 100%; max-height: 120mm; display: block; margin: 8pt auto; page-break-inside: avoid; }}
a {{ color: inherit; text-decoration: none; }}
section.front {{ page-break-before: always; }} section.first {{ page-break-before: auto; }}
.centre {{ text-align: center; padding-top: 40mm; }} .centre p {{ text-align: center; }}
.first p:first-child {{ font-size: 26pt; line-height: 1.2; margin-bottom: 8pt; }}
.small {{ padding-top: 60mm; }} .small p {{ font-size: 8pt; text-align: left; margin: 0 0 5pt; }}
</style>
{body}
</html>"""
    ph = f"{tmp}/print.html"
    open(ph, "w", encoding="utf-8").write(page.replace('src="' + tmp, 'src="file://' + tmp))
    cp = f"{tmp}/cover.html"
    open(cp, "w").write(f'<!doctype html><style>@page{{size:A5;margin:0}}html,body{{margin:0}}img{{width:148mm;'
                        f'height:209.5mm;display:block;object-fit:cover}}</style>'
                        f'<img src="file://{os.path.abspath(out)}/cover.jpg">')
    for page_file, pdf in ((cp, "cover.pdf"), (ph, "inside.pdf")):
        subprocess.run([CHROME, "--headless", "--no-sandbox", "--allow-file-access-from-files",
                        "--no-pdf-header-footer", f"--print-to-pdf={tmp}/{pdf}", "file://" + page_file],
                       check=True, capture_output=True)
    subprocess.run(["pdfunite", f"{tmp}/cover.pdf", f"{tmp}/inside.pdf", f"{tmp}/{slug}.pdf"], check=True)

    for ext in ("epub", "pdf"):
        print(f"{slug}.{ext}: {os.path.getsize(f'{tmp}/{slug}.{ext}') // 1024} KB")
        lock.lock_file(f"{tmp}/{slug}.{ext}", f"{out}/{slug}.{ext}.locked", tier="paid")
    with open(f"{out}/stats.json", "w", encoding="utf-8") as f:
        json.dump({"chapters": chapters, "words": words}, f)
        f.write("\n")
    shutil.rmtree(tmp)
    print(f"{chapters} chapters, {words:,} words; locked for paid subscribers")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
