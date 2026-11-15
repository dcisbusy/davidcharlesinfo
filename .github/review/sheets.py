"""One-off: download the book photos listed in images.json and lay them out as numbered contact sheets."""
import json, io, urllib.request, urllib.parse, re
from PIL import Image, ImageDraw
items = json.load(open(".github/review/images.json"))
cells = []
for it in items:
    u = it["url"]
    m = re.search(r"/(https?%3A%2F%2F[^?\s]+)$", u)
    orig = urllib.parse.unquote(m.group(1)) if m else u
    im = None
    for t in (f"https://substackcdn.com/image/fetch/w_480,c_limit,f_jpg,q_70/{urllib.parse.quote(orig, safe='')}", orig, u):
        try:
            data = urllib.request.urlopen(urllib.request.Request(t, headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read()
            im = Image.open(io.BytesIO(data)).convert("RGB"); break
        except Exception as e:
            print("fail", it["id"], t[:80], e)
    cells.append((it["id"], im))
W, H, COLS, ROWS = 400, 300, 4, 4
for n in range(0, len(cells), COLS * ROWS):
    sheet = Image.new("RGB", (W * COLS, (H + 24) * ROWS), "white"); d = ImageDraw.Draw(sheet)
    for i, (cid, im) in enumerate(cells[n:n + COLS * ROWS]):
        x, y = (i % COLS) * W, (i // COLS) * (H + 24)
        if im:
            im.thumbnail((W - 6, H)); sheet.paste(im, (x + 3, y + 22))
        d.rectangle((x, y, x + 120, y + 20), fill="black"); d.text((x + 4, y + 4), cid, fill="yellow")
    sheet.save(f"review-sheets/sheet-{n // (COLS * ROWS):02d}.jpg", quality=80)
