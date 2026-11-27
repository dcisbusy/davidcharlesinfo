"""Turn the Nature Evidence Library (a Claude Doc, exported as Markdown) into David's private library page.

    PAID_SUBSCRIBER_PASSWORD='…' python3 scripts/make_evidence.py "The Nature Evidence Library.md"

Writes evidence/library.locked: the library as HTML, locked with the paid subscribers' key (scripts/lock.py), so
only David opens it while paid subscriptions are paused. The page around it (/evidence/) is build_evidence() in
scripts/extras.py. The Markdown itself is never committed: the repository is public. Needs `pip install markdown`.
"""
import html
import os
import re
import sys

import markdown

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lock  # noqa: E402

MD = markdown.Markdown(extensions=["tables", "sane_lists"])


def md(text):
    MD.reset()
    out = MD.convert(text.strip())
    return out.replace('<a href="http', '<a target="_blank" rel="noopener" href="http')


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", html.unescape(t).lower()).strip("-")[:60]


def stars(title):
    """'Lunchtime walks — ★★★ (note)' -> ('Lunchtime walks', 3, '★★★ (note)'); the lowest count when a range."""
    m = re.search(r"\s+[—–-]\s+(★.*)$", title)
    if not m:
        return title, 0, ""
    counts = [len(g) for g in re.findall(r"★+", m.group(1))]
    return title[:m.start()], min(counts), m.group(1)


def entry(title, body, section):
    name, n, label = stars(title)
    # "**Study.** what it found **Use:** how to use it **Caveat:** the catch" -> labelled parts
    parts = re.split(r"\*\*(Use|Caveat):\*\*", body)
    main = md(parts[0])
    extra = ""
    for kind, text in zip(parts[1::2], parts[2::2]):
        cls = "use" if kind == "Use" else "caveat"
        inner = md(text)
        inner = re.sub(r"^<p>|</p>$", "", inner.strip())
        copy = '<button class="ev-copy" type="button" title="Copy this line">Copy</button>' if cls == "use" else ""
        extra += f'<div class="ev-{cls}"><span class="ev-tag">{kind}</span><div class="ev-text">{inner}</div>{copy}</div>'
    badge = (f'<span class="ev-stars" title="{html.escape(label)}">{"★" * n}<span class="ev-off">{"★" * (4 - n)}</span>'
             + (f'<small>{html.escape(re.sub(r"^★+( to ★+)?", "", label).strip(" ()"))}</small>' if re.sub(r"^★+( to ★+)?", "", label).strip() else "")
             + '</span>') if n else ""
    return (f'<article class="ev-card" id="{slug(name)}" data-stars="{n}" data-section="{section}">'
            f'<header><h3>{html.escape(name)}</h3>{badge}</header>{main}{extra}</article>')


LADDER_LINKS = [("40 seconds", "seconds-to-30-minutes-micro-breaks-and-lunchtimes"),
                ("15 to 30", "seconds-to-30-minutes-micro-breaks-and-lunchtimes"),
                ("120 minutes", "it-adds-up-120-minutes-a-week"),
                ("60 to 90", "one-walk-60-to-90-minutes-by-day"), ("Night", "night-and-darkness"),
                ("8 to 12", "regular-programmes-8-sessions-of-3-hours-and-similar"),
                ("Overnight", "overnight-residential-and-multi-day")]


def ladder(intro):
    """The 'At a glance' table (time out / benefit / strength) as a row of steps from seconds to a week."""
    m = re.search(r"\| Time out \|.*?\n\|[- |]+\|\n((?:\|.*\|\n?)+)", intro)
    if not m:
        return intro, ""
    steps = []
    for row in m.group(1).strip().splitlines():
        t, benefit, strength = [c.strip() for c in row.strip("|").split("|")]
        href = next((h for k, h in LADDER_LINKS if t.startswith(k)), "")
        n = min(len(g) for g in re.findall(r"★+", strength)) if "★" in strength else 0
        note = re.sub(r"★+( to ★+)?", "", strength).strip(" ()")
        steps.append(f'<li><a href="#{href}"><span class="t">{html.escape(t)}</span><span class="b">{html.escape(benefit)}</span>'
                     f'<span class="s" title="{html.escape(strength)}">{"★" * n}<span class="ev-off">{"★" * (4 - n)}</span>'
                     + (f'<small>{html.escape(note)}</small>' if note else "") + '</span></a></li>')
    intro = intro[:m.start()].rstrip() + "\n\n" + intro[m.end():]
    intro = re.sub(r"\*\*At a glance: what each length of session is good for\*\*\s*", "", intro)
    return intro, f'<p class="ev-ladder-h"><strong>At a glance: what each length of time is good for</strong></p><ol class="ev-ladder">{"".join(steps)}</ol>'


def build(src):
    text = open(src, encoding="utf-8").read().replace(" ", " ")
    text = re.sub(r"^# .*\n+(.*· @David\n+)?", "", text, count=1)          # the doc's title and byline
    intro, _, rest = text.partition("\n## ")
    sections = ("## " + rest).split("\n## ")
    toc, out = [], []
    for raw in sections:
        raw = raw.lstrip("# ")
        head, _, body = raw.partition("\n")
        sid = slug(head)
        lead, *entries = re.split(r"\n### ", "\n" + body)
        cards = []
        for e in entries:
            t, _, b = e.partition("\n")
            cards.append(entry(t.strip(), b, sid))
        lead, steps = ladder(lead)
        out.append(f'<section class="ev-sec" id="{sid}"><h2>{html.escape(head.strip())}</h2>'
                   f'<div class="ev-lead">{md(lead)}</div>{steps}' + (f'<div class="ev-cards">{"".join(cards)}</div>' if cards else "")
                   + '</section>')
        toc.append((sid, head.strip(), len(cards)))
    nav = "".join(f'<li><a href="#{s}">{html.escape(h)}</a>' + (f' <span>{n}</span>' if n else "") + '</li>'
                  for s, h, n in toc)
    n_entries = sum(n for _, _, n in toc)
    return (f'<div class="ev-intro">{md(intro)}</div>'
            f'<p class="ev-count-all">{n_entries} studies and summaries in {len(toc)} sections.</p>'
            f'<div class="ev-layout"><nav class="ev-toc" aria-label="Sections"><ol>{nav}</ol></nav>'
            f'<div class="ev-main">{"".join(out)}</div></div>')


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    lock.content_key(create=False, tier="paid")
    page = build(sys.argv[1])
    os.makedirs("evidence", exist_ok=True)
    with open("evidence/library.locked", "wb") as f:
        f.write(lock.lock_bytes(page.encode("utf-8"), tier="paid"))
    print(f"evidence/library.locked: {len(page) // 1024} KB of HTML, locked for the paid key")
