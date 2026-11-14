"""Words that are special to David: a corpus comparison for the 20 years in numbers page.

    pip install wordfreq        # once
    python3 scripts/keywords.py # writes data/keywords.json; the next build shows it on /numbers/

Every word in every story is counted and compared with how often it turns up in everyday English
(the wordfreq package: a blend of books, news, Wikipedia, subtitles, web text and social media).
A word's "keyness" is its log-likelihood score (Dunning's G2): high when it's both much more common here
than in English generally AND used often enough to be more than a fluke. The page shows

  words  - ordinary words used far more than usual (the ones that are mostly lower case)
  names  - people, places and projects (mostly written with a capital letter)
  eras   - for 2005-2012, 2013-2019 and 2020-now, the words that era uses most compared with the other two

Run it again now and then (say once a year); it isn't part of the nightly build because wordfreq is a
large download.
"""
import collections
import contextlib
import datetime
import io
import json
import math
import os
import re
import sys

from wordfreq import word_frequency

sys.path.insert(0, os.path.dirname(__file__))
import build  # noqa: E402

sys.modules["build"] = build
import extras  # noqa: E402

# Newsletter footers, web addresses and other words that say nothing about the writing itself
BOILERPLATE = set("""
davidcharles substack dcisbusy www org com http https paypal unsubscribe subscriber subscribers subscribe
subscribed subscribing mailing newsletter newsletters kottke vimeo youtube documentally html utm email emails inbox
wordpress blog blogs twitter facebook instagram patreon podcast mailchimp url pdf jpg png faq dave david charles
info pages page reply replies credits credit unlock welcome thank thanks thanking edition editions percent readers reader
archive hello name comment comments download downloads paying contribution contributions click link links posted
post posts issue issues free paid share sharing week weeks friday sign signup website site online via etc ps
learned learnt write writes writing wrote written writer story stories words word
""".split())
ERAS = (("2005–2012", "2005", "2012"), ("2013–2019", "2013", "2019"), ("2020–now", "2020", "9999"))
TOKEN = re.compile(r"[A-Za-z][A-Za-z'’]*[A-Za-z]")


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        issues = json.load(open(build.NEWSLETTER_DATA, encoding="utf-8"))
        entries = json.load(open(build.BLOG_DATA, encoding="utf-8"))
        stories, _ = extras.load_stories(issues, entries)
    count, capital, docs = collections.Counter(), collections.Counter(), collections.Counter()
    era_count = {e[0]: collections.Counter() for e in ERAS}
    total = 0
    for s in stories:
        if not s["has_text"]:
            continue
        toks = TOKEN.findall(s["text"])
        low = [t.lower().replace("’", "'") for t in toks]
        for t, w in zip(toks, low):
            if t[0].isupper():
                capital[w] += 1
        total += len(low)
        count.update(low)
        docs.update(set(low))
        era = next(e[0] for e in ERAS if e[1] <= s["date"][:4] <= e[2])
        era_count[era].update(low)

    def usable(w, min_count=20, min_docs=8):
        return (count[w] >= min_count and docs[w] >= min_docs and len(w) >= 3 and w not in BOILERPLATE
                and not w.endswith("'s") and w not in extras.STOP)

    def is_name(w):
        return capital[w] / count[w] > 0.7

    words, names = [], []
    for w, c in count.items():
        if not usable(w):
            continue
        f = word_frequency(w, "en")
        if not f:
            continue                         # not in the dictionary at all: usually a typo or a web address
        ratio = (c / total) / f
        if ratio < 6:
            continue
        expected = total * f
        g2 = 2 * (c * math.log(c / expected) - (c - expected))
        (names if is_name(w) else words).append({"w": w, "n": c, "x": round(ratio), "g2": round(g2)})
    words.sort(key=lambda r: -r["g2"])
    names.sort(key=lambda r: -r["g2"])

    eras = {}
    for era, _, _ in ERAS:
        a_total = sum(era_count[era].values())
        b_total = total - a_total
        out = []
        for w, a in era_count[era].items():
            if a < 12 or not usable(w, 12, 4) or is_name(w) or len(w) < 4:
                continue
            b = count[w] - a
            e1, e2 = a_total * (a + b) / total, b_total * (a + b) / total
            g2 = 2 * (a * math.log(a / e1) + (b * math.log(b / e2) if b else 0))
            if a / a_total > 2 * (b + 0.5) / b_total:          # at least twice as common as in the other eras
                out.append((g2, w, a))
        out.sort(reverse=True)
        eras[era] = [{"w": w, "n": a} for _, w, a in out[:16]]

    data = {"_note": "Made by scripts/keywords.py. Don't edit by hand; rerun the script.",
            "made": datetime.date.today().isoformat(), "total_words": total,
            "words": words[:60], "names": names[:40], "eras": eras}
    with open("data/keywords.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{total:,} words; {len(words)} special words, {len(names)} names")
    print("Words:", ", ".join(r["w"] for r in words[:40]))
    print("Names:", ", ".join(r["w"] for r in names[:25]))
    for era, ws in eras.items():
        print(era + ":", ", ".join(r["w"] for r in ws))


if __name__ == "__main__":
    main()
