"""Share cards: the 1200x630 picture shown when a page is shared on WhatsApp, Bluesky, Facebook, LinkedIn etc.

    python3 scripts/make_cards.py            # make cards that are missing or out of date
    python3 scripts/make_cards.py --all      # remake every card

One card per blog post and page, plus the series, books, timeline and other main pages. Each card is the
story's own photo with its title, or a plain card in the site colours when there is no photo. Cards are saved
in cards/ (named after the page address) and listed in cards/index.json with a fingerprint of the title and
photo, so only changed pages are redrawn. build.py uses a page's card as its og:image when one exists.

Needs Pillow and the fonts Lora and Inter (on GitHub: Actions -> Make ebook installs the same fonts).
"""
import glob
import hashlib
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import build  # noqa: E402

sys.modules["build"] = build
import extras  # noqa: E402

W, H = 1200, 630
CREAM, INK, ACCENT, RUST = (243, 234, 216), (34, 30, 24), (31, 122, 82), (180, 86, 43)


def font(kind, size):
    paths = {
        "serif": ["/usr/share/fonts/truetype/google-fonts/Lora-Variable.ttf", os.path.expanduser("~/.fonts/Lora.ttf")],
        "sans": ["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf", os.path.expanduser("~/.fonts/Inter.ttf")],
    }[kind]
    for p in paths:
        if os.path.exists(p):
            f = ImageFont.truetype(p, size)
            try:
                f.set_variation_by_name("Bold" if kind == "serif" else "SemiBold")
            except Exception:  # noqa: BLE001 - static fonts have no variations
                pass
            return f
    return ImageFont.load_default(size)


def card_path(url):
    slug = url.strip("/").replace("/", "--") or "home"
    return f"cards/{slug}.jpg"


def wrap(draw, text, fnt, width):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def fit_title(draw, title, width, max_lines, sizes):
    for size in sizes:
        fnt = font("serif", size)
        lines = wrap(draw, title, fnt, width)
        if len(lines) <= max_lines:
            return fnt, lines, size
    fnt = font("serif", sizes[-1])
    lines = wrap(draw, title, fnt, width)[:max_lines]
    lines[-1] = lines[-1].rstrip(" ,.:;") + "…"
    return fnt, lines, sizes[-1]


def load_photo(src):
    if not src or not src.startswith("/"):
        return None
    f = src.split("?")[0].lstrip("/")
    full = re.sub(r"-\d+x\d+(?=\.\w+$)", "", f)
    for p in (full, f):
        if os.path.exists(p):
            try:
                im = Image.open(p)
                if im.width < 500 or im.height < 260:
                    continue
                return im.convert("RGB")
            except Exception:  # noqa: BLE001
                continue
    return None


def draw_card(title, kicker, photo, out):
    if photo:
        scale = max(W / photo.width, H / photo.height)
        im = photo.resize((round(photo.width * scale), round(photo.height * scale)), Image.LANCZOS)
        left, top = (im.width - W) // 2, (im.height - H) // 3
        im = im.crop((left, top, left + W, top + H))
        # dark fade from the bottom so white text always reads
        fade = Image.new("L", (1, H))
        for y in range(H):
            fade.putpixel((0, y), int(235 * max(0, (y - H * 0.25) / (H * 0.75)) ** 1.3))
        shade = Image.new("RGB", (W, H), (12, 10, 8))
        im = Image.composite(shade, im, fade.resize((W, H)))
        d = ImageDraw.Draw(im)
        fnt, lines, size = fit_title(d, title, W - 140, 3, [68, 60, 54, 48, 42])
        lh = int(size * 1.18)
        y = H - 70 - lh * len(lines)
        d.text((70, y - 52), kicker.upper(), font=font("sans", 24), fill=(255, 214, 160))
        f = font("sans", 22)
        d.text((W - 60 - d.textlength("davidcharles.info", font=f), H - 50), "davidcharles.info", font=f,
               fill=(225, 220, 210))
        for i, line in enumerate(lines):
            d.text((70, y + i * lh), line, font=fnt, fill=(255, 255, 255))
    else:
        im = Image.new("RGB", (W, H), CREAM)
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 18, H), fill=ACCENT)
        fnt, lines, size = fit_title(d, title, W - 200, 4, [76, 68, 60, 54, 48])
        lh = int(size * 1.18)
        y = (H - lh * len(lines)) // 2 + 20
        d.text((90, y - 70), kicker.upper(), font=font("sans", 26), fill=RUST)
        for i, line in enumerate(lines):
            d.text((90, y + i * lh), line, font=fnt, fill=INK)
        d.text((90, H - 80), "davidcharles.info", font=font("sans", 26), fill=(110, 98, 84))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, "JPEG", quality=82, optimize=True, progressive=True)


def tree_backdrop():
    """The tree map's own trees as dots: a picture of the area made of nothing but trees."""
    try:   # the data is locked for subscribers (scripts/lock.py), so this needs SUBSCRIBER_PASSWORD
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import lock
        lines = lock.unlock_bytes(open("trees/trees-data.txt.locked", "rb").read()).decode("utf-8").split("\n")
        cats = json.loads(lock.unlock_bytes(open("trees/trees-lookup.json.locked", "rb").read()))["locations"]
    except Exception:
        return None
    colours = {"Highways": (226, 161, 61), "Parks": (120, 170, 120), "Housing": (154, 181, 150), "Other": (138, 132, 120)}
    lat0, lon0, zoom = 51.4215, -0.062, 14000          # centre on Crystal Palace, pixels per degree of latitude
    kx = zoom * 0.623                                    # cos(51.4°): longitude degrees are shorter
    im = Image.new("RGB", (W, H), (22, 29, 36))
    d = ImageDraw.Draw(im)
    for line in lines:
        p = line.split("|")
        if len(p) < 5:
            continue
        x = W / 2 + (float(p[2]) - lon0) * kx * 1.0
        y = H / 2 - (float(p[1]) - lat0) * zoom
        if 0 <= x < W and 0 <= y < H:
            c = colours.get(cats[int(p[4])] if p[4].isdigit() and int(p[4]) < len(cats) else "Other")
            d.ellipse((x - 1.1, y - 1.1, x + 1.1, y + 1.1), fill=c)
    return im


def targets():
    """(url, title, kicker, photo) for every page that gets a card."""
    issues = json.load(open(build.NEWSLETTER_DATA, encoding="utf-8"))
    entries = json.load(open(build.BLOG_DATA, encoding="utf-8"))
    stories, _ = extras.load_stories(issues, entries)
    common = extras.common_photos(stories)
    skip = extras.skip_words()
    story_of_blog = {s.get("blog_url"): s for s in stories if s.get("blog_url")}
    out = []
    for e in entries:
        path = build.file_for(e["url"])
        if not os.path.exists(path):
            continue
        m = build.CONTENT_RE.search(open(path, encoding="utf-8").read())
        st = {"html": m.group(1) if m else "", "image": e.get("image"), "source": "blog"}
        photo = next((u for u in extras.photo_candidates(st) if u.startswith("/")
                      and extras.img_key(u) not in common and not any(w in u for w in skip)), None)
        if not photo and story_of_blog.get(e["url"]):
            photo = extras.story_photo(story_of_blog[e["url"]], common)
        year = (e.get("date") or "")[:4]
        kicker = f"David Charles · {year}" if e["type"] == "post" and year else "David Charles"
        out.append((e["url"], e["title"], kicker, photo))
    for f in glob.glob("series/*/index.html"):
        t = open(f, encoding="utf-8").read()
        name = re.search(r"<h1>(.*?)</h1>", t)
        hero = re.search(r'<figure class="series-hero"><img src="([^"]+)"', t)
        if name:
            out.append(("/" + os.path.dirname(f) + "/", build.html.unescape(name.group(1)), "A series by David Charles",
                        hero.group(1) if hero else None))
    for b in json.load(open("data/books.json", encoding="utf-8")).get("books", []):
        out.append((f'/books/{b["slug"]}/', b["title"], "A free ebook by David Charles", b.get("cover_photo")))
    for url, title, kicker in (("/", "Twenty years of stories about adventure, nature and being human",
                                "David Charles"),
                               ("/timeline/", "Twenty years: a timeline", "David Charles"),
                               ("/series/", "Stories told in parts, from bike rides to book clubs", "David Charles"),
                               ("/map/", "Adventure map: where the stories happened", "David Charles"),
                               ("/random-story/", "Pick me a story", "David Charles"),
                               ("/start-here/", "Start here", "David Charles"),
                               ("/newsletter-archive/", "Every issue of the newsletter", "David Charles"),
                               ("/books/", "Free ebooks", "David Charles"),
                               ("/subscribers/", "Ebooks and maps for newsletter subscribers", "David Charles")):
        hero = json.load(open("data/start-here.json", encoding="utf-8")).get("hero") if url == "/start-here/" else None
        out.append((url, title, kicker, hero))
    if os.path.exists("trees/trees-data.txt.locked"):
        out.append(("/trees/", "Tree map: tap any tree to find out what it is",
                    "Crystal Palace · Norwood · Beckenham · Sydenham", "trees"))
    return out


def main(force=False):
    os.makedirs("cards", exist_ok=True)
    index_file = "cards/index.json"
    index = json.load(open(index_file, encoding="utf-8")) if os.path.exists(index_file) and not force else {}
    made = 0
    for url, title, kicker, photo in targets():
        title = build.html.unescape(title)
        fp = hashlib.sha1(json.dumps([title, kicker, photo, 3]).encode()).hexdigest()[:12]
        out = card_path(url)
        if index.get(url) == fp and os.path.exists(out):
            continue
        draw_card(title, kicker, tree_backdrop() if photo == "trees" else load_photo(photo), out)
        index[url] = fp
        made += 1
    json.dump(dict(sorted(index.items())), open(index_file, "w", encoding="utf-8"), indent=0)
    print(f"{made} share cards made; {len(index)} in total")


if __name__ == "__main__":
    main(force="--all" in sys.argv)
