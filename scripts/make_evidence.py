"""Turn the Nature Evidence Library (Markdown) into David's private library page.

    PAID_SUBSCRIBER_PASSWORD='…' python3 scripts/make_evidence.py                 # rebuild from the stored copy
    PAID_SUBSCRIBER_PASSWORD='…' python3 scripts/make_evidence.py library.md      # replace the stored copy, then rebuild

The Markdown lives in the repository only locked (evidence/library.md.locked, paid key), because the repository is
public. David edits it in his browser at /evidence/edit/, which locks and saves it; the "Evidence library" workflow
then runs this script, which writes evidence/library.locked: the page's HTML, locked with the same key. The page
around it (/evidence/) is build_evidence() in scripts/extras.py. Needs `pip install markdown cryptography`.
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
    out = out.replace('<a href="http', '<a target="_blank" rel="noopener" href="http')
    return out.replace('<a class="ev-ref" href="http', '<a class="ev-ref" target="_blank" rel="noopener" href="http')


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", html.unescape(t).lower()).strip("-")[:60]


def stars(title):
    """'Lunchtime walks — ★★★ (note)' -> ('Lunchtime walks', 3, '★★★ (note)'); the lowest count when a range."""
    m = re.search(r"\s+[—–-]\s+(★.*)$", title)
    if not m:
        return title, 0, ""
    counts = [len(g) for g in re.findall(r"★+", m.group(1))]
    return title[:m.start()], min(counts), m.group(1)


# Studies the references list gives without a link, or that the text cites without a references entry. Found by
# searching; the journal's DOI where there is one, otherwise the report or an open repository copy.
MISSING_URLS = {
    ("Marselle", "2014"): "https://doi.org/10.1089/eco.2014.0027",
    ("Bell", "2014"): "https://pureportal.coventry.ac.uk/en/publications/dark-nature-exploring-potential-benefits-of-nocturnal-nature-base-2/",
    ("Rogerson", "2017"): "https://teesvalleynaturepartnership.org.uk/wp-content/uploads/2019/09/Health-wellbeing-volunteering-with-WTs.pdf",
    ("Hattie", "1997"): "https://doi.org/10.3102/00346543067001043",
    ("Naor", "2020"): "https://doi.org/10.3389/fpsyg.2020.547067",
    ("Koo", "2008"): "https://doi.org/10.1037/a0013316",
    ("Taylor", ""): "https://blogs.uoregon.edu/richardtaylor/?p=308",
}
# Phrases in the text that point at a source without "Surname (Year)": linked as written, first time in each card.
PHRASE_LINKS = [
    ("Nature Connectedness at Night (University of Derby with Buglife, ongoing)", "https://www.buglife.org.uk/blog/step-outside-after-dark/"),
    ("Nature Connectedness at Night (Derby/Buglife)", "https://www.buglife.org.uk/blog/step-outside-after-dark/"),
    ("North York Moors dark-sky research", "https://ray.yorksj.ac.uk/id/eprint/13954/"),
    ("Leeds research with women in parks", "https://doi.org/10.48785/100/108"),
    ("82% of women in Great Britain", "https://www.ons.gov.uk/peoplepopulationandcommunity/crimeandjustice/bulletins/perceptionsofpersonalsafetyandexperiencesofharassmentgreatbritain/latest"),
    ("Richardson and colleagues (2017–2025)", "https://doi.org/10.1080/21711976.2016.1267136"),
    ("Physicist Richard Taylor", "https://blogs.uoregon.edu/richardtaylor/?p=308"),
    ("Fractal fluency (Taylor)", "https://blogs.uoregon.edu/richardtaylor/?p=308"),
    ("Palmer et al., 2026", "https://doi.org/10.1002/pan3.70317"),
    ("The Mother Nature Project", "https://bristolbrc.nihr.ac.uk/research/research-projects/developing-and-testing-a-nature-based-intervention-for-mothers-with-postnatal-depression"),
    ("Barnes (2025)", "https://doi.org/10.48773/qzx15"),
    ("A global meta-analysis in Conservation Letters (2021)", "https://doi.org/10.1111/conl.12852"),
    ("Freeman et al. (UK)", "https://doi.org/10.1093/heapro/daw036"),
    ("a week of camping moved sleep-hormone timing", "https://doi.org/10.1016/j.cub.2013.06.039"),
    ("a single weekend did most of that", "https://doi.org/10.1016/j.cub.2016.12.041"),
    ("most women in Britain feel unsafe in parks after dark", "https://www.ons.gov.uk/peoplepopulationandcommunity/crimeandjustice/bulletins/perceptionsofpersonalsafetyandexperiencesofharassmentgreatbritain/latest"),
    ("The 2018 paper", "https://doi.org/10.1037/emo0000442"),
    ("US Senate Finance Committee investigation", "https://www.finance.senate.gov/imo/media/doc/sfc_report_warehouses_of_neglect.pdf"),
    ("UKHSA says", "https://ukhsa.blog.gov.uk/2024/03/21/what-is-lyme-disease-and-why-do-we-need-to-be-tick-aware/"),
    ("Natural England (2026)", "https://www.gov.uk/government/statistics/the-people-and-nature-survey-for-england-adult-data-y1q1-april-june-2020-experimental-statistics/the-people-and-nature-survey-for-england-adult-data-y1q1-april-june-2020-experimental-statistics"),
]
REFS = {}          # surname -> {year: url}, filled from the references section by parse_refs()


def parse_refs(section):
    """Each '- Surname, A. et al. (2019). … [doi](url)' line -> REFS[surname][year] = url (MISSING_URLS fills gaps)."""
    for line in section.splitlines():
        if not re.match(r"[-*] ", line):
            continue
        name = re.split(r",| \(", line[2:], maxsplit=1)[0].strip()
        year = (re.search(r"\((\d{4})", line) or [None, ""])[1]
        url = re.search(r"\]\(<?(https?://[^\s>]+?)>?\)(?:\s|$|\.)", line)
        doi = re.search(r"\bdoi:(10\.\S+?)\.?$", line)
        url = url[1] if url else ("https://doi.org/" + doi[1]) if doi else MISSING_URLS.get((name, year), "")
        if url:
            REFS.setdefault(name, {})[year] = url
    for (name, year), url in MISSING_URLS.items():
        REFS.setdefault(name, {}).setdefault(year, url)


def a(text, url):
    return f'<a class="ev-ref" href="{html.escape(url)}">{text}</a>'


def cite(text):
    """Turn every 'Surname … (Year)', 'Surname et al., Year' and known phrase into a link to the study."""
    taken = [m.span() for m in re.finditer(r"\[[^\]]*\]\([^)]*\)|<a .*?</a>", text)]
    hits = []
    for name, years in REFS.items():
        n = re.escape(name)
        pats = [rf"\b{n}\b(?:[^()\n\[\]*.;]|(?<=al)\.){{0,60}}?\([^()\n]*?(\d{{4}})[^()\n]*\)",     # Hunter et al. (2019)
                rf"\b{n}\b(?: et al\.)?,? (\d{{4}})\b"]                              # (Nguyen et al., 2023)
        if len(years) == 1:
            pats.append(rf"\b{n}(?: et al\.)()")                                     # Sturm et al. found…
        for pat in pats:
            for m in re.finditer(pat, text):
                url = years.get(m[1]) if m[1] else next(iter(years.values()))
                if url:
                    hits.append((m.start(), m.end(), url))
    for phrase, url in PHRASE_LINKS:
        i = text.find(phrase)
        if i >= 0:
            hits.append((i, i + len(phrase), url))
    out, last = [], 0
    for s, e, url in sorted(hits, key=lambda h: (h[0], -h[1])):
        if s < last or any(s < te and e > ts for ts, te in taken):
            continue
        out += [text[last:s], a(text[s:e], url)]
        last = e
    return "".join(out) + text[last:]


def link_refs(section):
    """Give each reference that has no link one: '… 6(3), 134–147. [link](url)'."""
    lines = []
    for line in section.splitlines():
        line = line.replace("*Curr*ent Biology", "*Current Biology*")
        bare = re.search(r"\bdoi:(10\.\S+?)\.?$", line)
        if bare and "](" not in line:
            line = line[:bare.start()] + f"[doi:{bare[1]}](https://doi.org/{bare[1]})"
        if re.match(r"[-*] ", line) and "](" not in line:
            name = re.split(r",| \(", line[2:], maxsplit=1)[0].strip()
            year = (re.search(r"\((\d{4})", line) or [None, ""])[1]
            url = REFS.get(name, {}).get(year)
            if url:
                line += f" [{'doi' if 'doi.org' in url else 'online'}]({url})"
        lines.append(line)
    return "\n".join(lines)


def entry(title, body, section):
    name, n, label = stars(title)
    # "**Study.** what it found **Use:** how to use it **Caveat:** the catch" -> labelled parts
    body = cite(body)
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
    parse_refs(next(x for x in sections if x.lstrip("# ").startswith("References")))
    toc, out = [], []
    for raw in sections:
        raw = raw.lstrip("# ")
        head, _, body = raw.partition("\n")
        sid = slug(head)
        if head.strip() == "References":
            body = link_refs(body)
        lead, *entries = re.split(r"\n### ", "\n" + body)
        if head.strip() != "References":
            lead = cite(lead)
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


SOURCE = "evidence/library.md.locked"

if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit(__doc__)
    lock.content_key(create=False, tier="paid")
    os.makedirs("evidence", exist_ok=True)
    if len(sys.argv) == 2:                     # a new copy of the Markdown: store it, locked
        text = open(sys.argv[1], encoding="utf-8").read()
        with open(SOURCE, "wb") as f:
            f.write(lock.lock_bytes(text.encode("utf-8"), tier="paid"))
        print(f"{SOURCE}: stored {len(text) // 1024} KB of Markdown, locked")
    text = lock.unlock_bytes(open(SOURCE, "rb").read(), tier="paid").decode("utf-8")
    tmp = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "evidence-library.md")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        page = build(tmp)
    finally:
        os.remove(tmp)
    with open("evidence/library.locked", "wb") as f:
        f.write(lock.lock_bytes(page.encode("utf-8"), tier="paid"))
    n = page.count('class="ev-card"')
    print(f"evidence/library.locked: {n} entries, {page.count('class=\"ev-ref\"')} study links, "
          f"{len(page) // 1024} KB of HTML, locked for the paid key")
