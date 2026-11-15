"""
The fun pages: adventure map, On this day, 20 years in numbers, photo wall.

They all work from one list of "stories": every newsletter issue, plus every
blog post that isn't a copy of a newsletter issue. Where a blog post copies a
newsletter issue, the story links to Substack and borrows the blog copy's text
and photos (Substack blocks us from reading issues directly).

Corrections go in data/story-overrides.json; places in data/places.json.
"""

import collections
import datetime
import html
import json
import math
import os
import re
import sys
from urllib.parse import quote

from build import (MONTHS, PERSON, SITE, SUBSTACK, TILE_COLOURS, chips, esc, file_for, nice, page, read, write_if_changed)

STOP = set("""
a about above after again against all am an and any are aren't as at be because been before being below between both
but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from further had
hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how how's i i'd
i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once
only or other ought our ours ourselves out over own same shan't she she'd she'll she's should shouldn't so some such
than that that's the their theirs them themselves then there there's these they they'd they'll they're they've this
those through to too under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's
where where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your yours
yourself yourselves just like also get got one two even much really still back way well can will make made going go
know think things thing something lot little bit day days time new now first last see said say says many every
another around us yes oh ok okay might must may though although via actually maybe perhaps quite rather enough
""".split())

NEWSLETTER_GREEN = "#1f7a52"     # validated pair (colour-blind safe, 3:1 on white)
BLOG_OCHRE = "#b7791f"


# ---------------------------------------------------------------- stories

def norm_words(t):
    return {w for w in re.findall(r"[a-z0-9]+", t.lower().replace("’", "'")) if w not in STOP and len(w) > 2}


def plain(h):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or ""))).strip()


EXPORT_DIRS = sorted(d for d in os.listdir(".") if d.startswith("substackpostsexport") and os.path.isdir(d))


def load_export():
    """Full text of newsletter issues from Substack export folders, by slug (newest export wins)."""
    out = {}
    for d in EXPORT_DIRS:
        # Sorted by post id, so if a slug appears twice the newest version wins
        for f in sorted(os.listdir(d), key=lambda f: int(f.split(".")[0]) if f.split(".")[0].isdigit() else 0):
            if f.endswith(".html") and "." in f[:-5]:
                out[f[:-5].split(".", 1)[1]] = os.path.join(d, f)
    return out


def issue_slug(url):
    return url.rstrip("/").split("/p/")[-1] if "/p/" in url else None


def load_stories(issues, entries):
    over = json.load(open("data/story-overrides.json", encoding="utf-8"))
    export = load_export()
    blog = [e for e in entries if e["type"] == "post"]
    content = {}
    for e in blog:
        s = read(file_for(e["url"])) or ""
        m = re.search(r"<!--content:start-->(.*?)<!--content:end-->", s, re.S)
        content[e["url"]] = m.group(1) if m else ""
    text = {u: plain(h) for u, h in content.items()}
    low = {u: t.lower() for u, t in text.items()}

    # Newsletter issues listed twice (same title and date) count once
    seen, nl = set(), []
    for i in issues:
        k = (re.sub(r"\W+", "", i["title"].lower()), i.get("date", ""))
        if k not in seen:
            seen.add(k)
            nl.append(i)

    def day(d):
        try:
            return datetime.date.fromisoformat(d[:10])
        except Exception:
            return None

    # Match each newsletter issue to the blog post that copies it (if any)
    candidates = []
    by_url = {e["url"]: e for e in blog}
    for i, n in enumerate(nl):
        nd = day(n.get("date", ""))
        if not nd:
            continue
        tw = norm_words(n["title"])
        ex = re.sub(r"\s+", " ", n.get("excerpt", "").lower())
        for e in blog:
            bd = day(e["date"])
            if not bd or abs((bd - nd).days) > 3:
                continue
            if e["url"] in over["not_duplicates"]:
                continue
            tov = len(tw & norm_words(e["title"])) / max(1, len(tw))
            exhit = len(ex) > 25 and ex[:40] in low[e["url"]]
            intext = sum(1 for w in tw if w in low[e["url"]]) / max(1, len(tw))
            score = tov * 2 + exhit * 2 + intext
            if score >= 2 or (tov >= 0.5 and abs((bd - nd).days) <= 1):
                candidates.append((score, i, e["url"]))
    pair_issue, pair_blog = {}, {}
    for score, i, u in sorted(candidates, reverse=True):
        if i not in pair_issue and u not in pair_blog:
            pair_issue[i], pair_blog[u] = u, i
    nl_index = {n["url"]: i for i, n in enumerate(nl)}
    for u, nurl in over["duplicates"].items():
        if u in by_url and nurl in nl_index:
            i = nl_index[nurl]
            pair_blog.pop(pair_issue.get(i), None)
            pair_issue[i], pair_blog[u] = u, i

    stories = []
    from_export = 0
    for i, n in enumerate(nl):
        b = pair_issue.get(i)
        ex_html = ""
        f = export.get(issue_slug(n["url"]) or "")
        if f and not n.get("paid"):
            ex_html = re.sub(r"^\s*<h1>.*?</h1>", "", read(f) or "", flags=re.S)
            from_export += 1
        if ex_html:
            body_text, body_html = plain(ex_html), ex_html
        elif b:
            body_text, body_html = text[b], content[b]
        else:
            body_text, body_html = f'{n["title"]}. {n.get("excerpt", "")}', ""
        stories.append({
            "title": n["title"], "date": n.get("date", ""), "url": n["url"], "source": "newsletter",
            "blog_url": b, "image": n.get("image") or (by_url[b].get("image") if b else None),
            "excerpt": n.get("excerpt", ""), "text": body_text, "html": body_html, "paid": bool(n.get("paid")),
            "comments": 0, "has_text": bool(ex_html or b),
        })
    for e in blog:
        if e["url"] in pair_blog:
            continue
        s = read(file_for(e["url"])) or ""
        stories.append({
            "title": e["title"], "date": e["date"], "url": e["url"], "source": "blog", "blog_url": e["url"],
            "image": e.get("image"), "excerpt": e.get("excerpt", ""), "text": text[e["url"]],
            "html": content[e["url"]], "comments": len(re.findall(r'<li id="comment-', s)), "has_text": True,
            "paid": False,
        })
    stories.sort(key=lambda s: (s["date"], s["title"]), reverse=True)
    print(f"{len(stories)} stories ({len(nl)} newsletter issues, {from_export} with full text from the Substack export, "
          f"{len(pair_blog)} blog copies matched, {len(blog) - len(pair_blog)} blog-only)")
    return stories, over


# ---------------------------------------------------------------- places and the map

def _km(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = (math.sin((la2 - la1) * p / 2) ** 2
         + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def find_places(stories, over):
    gaz = json.load(open("data/places.json", encoding="utf-8"))
    places, broad, skip = gaz["places"], set(gaz["broad"]) | {"London"}, set(gaz["skip_words"])
    names = sorted(places, key=len, reverse=True)
    plain_names = [n for n in names if n not in skip]
    any_re = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in plain_names) + r")(?![\w-])")
    body_re = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in plain_names) + r")(?![\w-])")
    ctx_re = re.compile(r"\b(?:in|to|at|from|near|around|across|of|via|on)\s+(" +
                        "|".join(re.escape(n) for n in skip) + r")(?![\w-])")
    not_re = re.compile("|".join(re.escape(p) for p in sorted(gaz.get("not_places", []), key=len, reverse=True)) or "(?!)")
    mentions = collections.Counter()
    for s in stories:
        if s["url"] in over["places"]:
            s["place"] = over["places"][s["url"]] or None
            continue
        score = collections.Counter()
        title, body = (not_re.sub(" ", t.replace("İ", "I").replace("ı", "i")) for t in (s["title"], s["text"]))
        for n in any_re.findall(title) + ctx_re.findall(title):
            score[n] += 6
        if re.search(r"(?:^|[\s:,–-])(" + "|".join(re.escape(n) for n in skip) + r")\s*[–:,-]", title + ":"):
            for n in re.findall(r"(?:^|[\s:,–-])(" + "|".join(re.escape(n) for n in skip) + r")(?=\s*[–:,-])", title + ":"):
                score[n] += 6
        # "Greetings from Perth", "a warm welcome from Thessaloniki", "coming to you live from Paris": where the
        # story was written from. A named place there almost always wins; nicknames like "the Palace" (see
        # opener_names in places.json) are a weaker hint, because those issues are often about somewhere else.
        g = re.search(r"(?i)\b(?:greetings|welcome|hello|writing|dispatch(?:es)?|postcard|coming to you(?: live)?)"
                      r"(?:,)?\s+(?:\w+\s+){0,2}?from\b(.{0,90})", body[:400])
        where = re.split(r"[.;:!?(—–]", g.group(1))[0] if g else ""
        if re.search(r"(?i)\b(?:train|carriage|drive|flight|plane|bus|road|ferry)\b", where):
            where = ""                                     # "a train rushing to London" says nothing
        opened = set()
        if where:
            opened = set(body_re.findall(where) + ctx_re.findall(" in " + where))
            for n in opened:
                score[n] += 12
            for nick, n in gaz.get("opener_names", {}).items():     # "from the Ness", "from the Palace"
                if re.match(r"(?i)\s+" + re.escape(nick) + r"\b(?! of)", where) and n in places:
                    score[n] += 4
        lead = body[:700]
        for n in body_re.findall(lead) + ctx_re.findall(lead):
            score[n] += 2
        for n in body_re.findall(body) + ctx_re.findall(body):
            score[n] += 1
        for n, c in score.items():
            mentions[n] += 1
        # A place gains half the score of every other mentioned place within 200 km (countries and regions
        # included), so a story full of Scottish places isn't pinned to one passing mention of Amsterdam.
        def cluster(n):
            la, lo = places[n]
            near = sum(c for m, c in score.items() if m != n and m in places and m != "London"
                       and _km(la, lo, *places[m]) <= 200)
            return score[n] + near / 2
        specific = [(cluster(n), score[n], n) for n in score if n not in broad and n in places]
        specific = [(cl, n) for cl, own, n in specific if own >= 3]
        general = [(c, n) for n, c in score.items() if n in broad]
        best = max(specific) if specific else None
        # A country or region the story is plainly about beats a passing mention of a specific place
        # ("My Albanian Love Affair" is about Albania, not the one line about Dartmoor).
        if best and general:
            gbest = max(general)
            if (gbest[1] != "London" or gbest[1] in opened) and gbest[0] >= 8 and score[best[1]] < 6 and gbest[0] >= 3 * score[best[1]]:
                best = None
        if best:
            s["place"] = best[1]
        elif general and max(general)[0] >= 6:
            s["place"] = max(general)[1]
        else:
            s["place"] = None
    for s in stories:
        if s.get("place") and s["place"] in places:
            s["coords"] = places[s["place"]]
        else:
            s["place"] = None
    return mentions


def build_map(stories):
    pins = [[round(s["coords"][0], 4), round(s["coords"][1], 4), s["title"], s["url"], s["date"], s["place"],
             s["source"]] for s in stories if s.get("place")]
    counts = collections.Counter(s["place"] for s in stories if s.get("place"))
    years = sorted({p[4][:4] for p in pins if p[4]}, reverse=True)
    top = "".join(f'<li><a href="#" data-place="{esc(n)}">{esc(n)} <span>{c}</span></a></li>'
                  for n, c in counts.most_common(40))
    pins_js = json.dumps(pins, ensure_ascii=False).replace("</", "<\\/")   # safe inside <script>
    body = f"""<h1>Adventure map</h1>
<p class="intro muted">{len(pins)} stories from {len(counts)} places, from the newsletter and the blog. Click a pin
(or a numbered cluster to zoom in), or pick a place below. Newsletter issues open on Substack.</p>
<div class="map-controls"><label for="year">Year</label> <select id="year"><option value="">All years</option>
{"".join(f'<option>{y}</option>' for y in years)}</select> <span id="count" class="muted"></span></div>
<div id="map" role="region" aria-label="Map of stories"></div>
<h2>Most-visited places</h2>
<ul class="chips" id="places">{top}</ul>
<p class="back"><a href="/trees/">Tree map: every tree around Crystal Palace</a> &middot; <a href="/numbers/">More in 20 years in numbers</a></p>
<link rel="stylesheet" href="/assets/leaflet/leaflet.css">
<link rel="stylesheet" href="/assets/leaflet/MarkerCluster.css">
<link rel="stylesheet" href="/assets/leaflet/MarkerCluster.Default.css">
<script src="/assets/leaflet/leaflet.js"></script>
<script src="/assets/leaflet/leaflet.markercluster.js"></script>
<script>
var PINS={pins_js};
var MONTHS={json.dumps(MONTHS)};
function nice(d){{var p=d.split('-');return p.length<3?d:(+p[2])+' '+MONTHS[+p[1]-1]+' '+p[0];}}
function escHtml(s){{return s.replace(/[&<>"]/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c];}});}}
var map=L.map('map',{{scrollWheelZoom:false}}).setView([48,8],4);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:18,
  attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}}).addTo(map);
var layer=L.markerClusterGroup({{showCoverageOnHover:false,maxClusterRadius:40}});
map.addLayer(layer);
var css=getComputedStyle(document.documentElement);
function col(v){{return css.getPropertyValue(v).trim();}}
var dot={{radius:7,weight:2,fillOpacity:1}};
function draw(){{
  var y=document.getElementById('year').value, n=0;
  layer.clearLayers();
  PINS.forEach(function(p){{
    if(y && p[4].slice(0,4)!==y) return; n++;
    var m=L.circleMarker([p[0]+(Math.random()-.5)*0.002,p[1]+(Math.random()-.5)*0.002],
      Object.assign({{fillColor:col(p[6]==='newsletter'?'--s0':'--s1'),color:col('--bg')}},dot));
    m.bindPopup('<strong><a href="'+escHtml(p[3])+'">'+escHtml(p[2])+'</a></strong><br><small>'+escHtml(p[5])+' &middot; '+nice(p[4])+
      (p[6]==='newsletter'?' &middot; newsletter':' &middot; blog')+'</small>');
    layer.addLayer(m);
  }});
  document.getElementById('count').textContent=n+' stories';
}}
document.getElementById('year').addEventListener('change',draw);
document.addEventListener('themechange',function(){{css=getComputedStyle(document.documentElement);draw();}});
document.querySelectorAll('#places a').forEach(function(a){{a.addEventListener('click',function(e){{
  e.preventDefault(); var name=a.getAttribute('data-place');
  var p=PINS.filter(function(x){{return x[5]===name;}})[0]; if(p){{map.setView([p[0],p[1]],10);
  document.getElementById('map').scrollIntoView({{behavior:'smooth',block:'center'}});}}
}});}});
draw();
</script>
<p class="muted small">Pins: <span class="key s0"></span> newsletter
<span class="key s1"></span> blog. Places are found automatically from each story's
words, so the odd pin may be in the wrong place.</p>"""
    write_if_changed("map/index.html", page("Adventure map | David Charles",
                                            f"{len(pins)} stories by David Charles, on a map.", "/map/", body, "/map/"))


# ---------------------------------------------------------------- On this day

def build_on_this_day(stories):
    days = collections.defaultdict(list)
    common = common_photos(stories)
    for s in stories:
        if len(s["date"]) >= 10:
            photo = re.sub(r"w_\d+,h_\d+,c_fill", "w_160,h_160,c_fill", story_photo(s, common) or "")   # small thumbnails
            days[s["date"][5:10]].append([int(s["date"][:4]), s["title"], s["url"], photo])
    for k in days:
        days[k].sort()
    write_if_changed("assets/on-this-day.json", json.dumps(days, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return """<section class="on-this-day" id="on-this-day" hidden>
<h2 class="section" id="otd-title">On this day</h2>
<ul class="otd" id="otd-list"></ul>
</section>
<script>
(function(){
  fetch('/assets/on-this-day.json').then(function(r){return r.json();}).then(function(D){
    var now=new Date(), year=now.getFullYear(), pad=function(n){return (n<10?'0':'')+n;};
    function key(d){return pad(d.getMonth()+1)+'-'+pad(d.getDate());}
    var items=(D[key(now)]||[]).filter(function(x){return x[0]<year;}), title='On this day';
    if(!items.length){
      for(var i=1;i<=3;i++){[-i,i].forEach(function(o){var d=new Date(now);d.setDate(d.getDate()+o);
        (D[key(d)]||[]).forEach(function(x){if(x[0]<year)items.push(x);});});}
      title='This week in years gone by';
    }
    if(!items.length) return;
    items.sort(function(a,b){return b[0]-a[0];});
    var ul=document.getElementById('otd-list');
    items.slice(0,6).forEach(function(x){
      var li=document.createElement('li'), a=document.createElement('a'), pic, div=document.createElement('div'),
          t=document.createElement('time'), b=document.createElement('span');
      if(x[3]){pic=document.createElement('img');pic.src=x[3];pic.alt='';pic.loading='lazy';
        pic.onerror=function(){this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',textContent:x[0]}));};}
      else{pic=Object.assign(document.createElement('span'),{className:'ph',textContent:x[0]});}
      t.textContent=(year-x[0])+(year-x[0]===1?' year ago':' years ago')+' \u00b7 '+x[0];
      b.className='t'; b.textContent=x[1]; a.href=x[2];
      div.appendChild(t); div.appendChild(b); a.appendChild(pic); a.appendChild(div); li.appendChild(a); ul.appendChild(li);
    });
    document.getElementById('otd-title').textContent=title;
    document.getElementById('on-this-day').hidden=false;
  }).catch(function(){});
})();
</script>"""


# ---------------------------------------------------------------- 20 years in numbers

def svg_bars(data, series, height=220, width=720, unit="", label_every=1):
    """Vertical (optionally stacked) bar chart. data: [(label, [v1, v2..])], series: [(name, colour)]."""
    pad_l, pad_b, pad_t = 44, 26, 10
    mx = max(sum(v) for _, v in data) or 1
    step = 10 ** max(0, len(str(int(mx))) - 1)
    top = ((int(mx) // step) + 1) * step
    plot_w, plot_h = width - pad_l - 6, height - pad_b - pad_t
    bw = plot_w / len(data)
    g = []
    for k in range(0, 5):
        v = top * k / 4
        y = pad_t + plot_h - plot_h * v / top
        g.append(f'<line x1="{pad_l}" x2="{width - 6}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                 f'<text x="{pad_l - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{(f"{v / 1000:g}k" if v >= 10000 else f"{int(v):,}")}</text>')
    for idx, (label, vals) in enumerate(data):
        x = pad_l + idx * bw + 2
        w = max(2, bw - 4)
        y0 = pad_t + plot_h
        last = max((i for i, v in enumerate(vals) if v), default=-1)
        for i, v in enumerate(vals):
            if not v:
                continue
            h = plot_h * v / top
            y = y0 - h
            name, colour = series[i]
            cls = f"s{i}"
            tip = f"{label}: {v:,}{unit}" + (f" ({name})" if len(series) > 1 else "")
            r = min(4, w / 2, h)
            if i == last:   # rounded top, square base
                d = (f"M{x:.1f},{y0:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + w - r:.1f} "
                     f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y0:.1f} Z")
                g.append(f'<path d="{d}" class="{cls}"><title>{esc(tip)}</title></path>')
            else:
                g.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{max(0, h - 2):.1f}" '
                         f'class="{cls}"><title>{esc(tip)}</title></rect>')
            y0 = y
        if idx % label_every == 0:
            g.append(f'<text x="{x + w / 2:.1f}" y="{height - 8}" class="tick" text-anchor="middle">{esc(label)}</text>')
    legend = ""
    if len(series) > 1:
        legend = '<p class="legend">' + "".join(
            f'<span><i class="s{i}"></i>{esc(n)}</span>' for i, (n, c) in enumerate(series)) + "</p>"
    return (legend + f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">' + "".join(g) + "</svg>")


def svg_hbars(data, colour=NEWSLETTER_GREEN, width=460, unit=""):
    row, pad_l = 26, 110
    height = row * len(data) + 6
    mx = max(v for _, v in data) or 1
    g = []
    for i, (label, v) in enumerate(data):
        y = 4 + i * row
        w = (width - pad_l - 60) * v / mx
        r = min(4, w / 2)
        d = (f"M{pad_l},{y + 3} H{pad_l + w - r:.1f} Q{pad_l + w:.1f},{y + 3} {pad_l + w:.1f},{y + 3 + r:.1f} "
             f"V{y + row - 7 - r:.1f} Q{pad_l + w:.1f},{y + row - 7} {pad_l + w - r:.1f},{y + row - 7} H{pad_l} Z")
        g.append(f'<text x="{pad_l - 8}" y="{y + row / 2 + 2:.1f}" class="label" text-anchor="end">{esc(label)}</text>'
                 f'<path d="{d}" class="s0"><title>{esc(label)}: {v:,}{unit}</title></path>'
                 f'<text x="{pad_l + w + 6:.1f}" y="{y + row / 2 + 2:.1f}" class="value">{v:,}{unit}</text>')
    return f'<svg class="chart hbars" viewBox="0 0 {width} {height}" role="img">' + "".join(g) + "</svg>"


def table(headers, rows):
    return ("<details class=\"data\"><summary>Show the numbers</summary><table><thead><tr>"
            + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in rows)
            + "</tbody></table></details>")


def keyword_section():
    """'Words that are special to me', from data/keywords.json (made by scripts/keywords.py)."""
    try:
        k = json.load(open("data/keywords.json", encoding="utf-8"))
    except (OSError, ValueError):
        return ""

    def cloud(rows, cls):
        if not rows:
            return ""
        top = max(math.log(r["g2"]) for r in rows)
        low = min(math.log(r["g2"]) for r in rows)
        return f'<p class="cloud {cls}">' + " ".join(
            f'<a href="/search/?q={esc(r["w"])}" style="font-size:{0.9 + 1.5 * (math.log(r["g2"]) - low) / ((top - low) or 1):.2f}em" '
            f'title="{r["n"]:,} times, {r["x"]:,}× more often than in everyday English">'
            f'{esc(r["w"].title() if cls == "kw-names" and r["w"] not in ("bbc", "lsd", "covid") else r["w"].upper() if cls == "kw-names" else r["w"])}</a>'
            for r in sorted(rows, key=lambda r: r["w"])) + "</p>"

    most = sorted([r for r in k["words"] if r["n"] >= 40], key=lambda r: -r["x"])[:10]
    mx = math.log10(most[0]["x"]) if most else 1
    bars = "".join(
        f'<li><a href="/search/?q={esc(r["w"])}">{esc(r["w"])}</a><span class="bar" style="width:{max(4, 100 * math.log10(r["x"]) / mx):.0f}%"></span>'
        f'<b>{r["x"]:,}×</b></li>' for r in most)
    eras = "".join(
        f'<div><h3>{esc(e)}</h3><p>' + " ".join(f'<a href="/search/?q={esc(r["w"])}">{esc(r["w"])}</a>' for r in ws)
        + "</p></div>" for e, ws in k["eras"].items())
    return f"""<h2 class="section">Words that are special to me</h2>
<p>Not the words I use most ("people", "life" and "good", like most writers), but the words I use far
more than most writers do. Each word in twenty years of stories is compared with how often it appears in everyday
English: books, news, Wikipedia, film subtitles and the web.</p>
<h3 class="kw-h">Most out of the ordinary</h3>
<p class="muted small">How many times more often I use these words than English in general.</p>
<ol class="kw-bars">{bars}</ol>
<h3 class="kw-h">My words</h3>
{cloud(k["words"], "kw-words")}
<h3 class="kw-h">My people, places and projects</h3>
{cloud(k["names"], "kw-names")}
<p class="muted small">Bigger means more distinctive: used both far more than usual and often enough to matter (a
log-likelihood score). Tap a word to find the stories it's in.</p>
<h3 class="kw-h">How the words changed</h3>
<div class="kw-eras">{eras}</div>
<p class="muted small">For each era, the words used at least twice as often as in the other two. Counted
{k["total_words"]:,} words, {nice(k["made"])}.</p>"""


def build_numbers(stories, mentions):
    for s in stories:
        s["words"] = len(re.findall(r"[A-Za-zÀ-ɏ'’-]+", s["text"])) if s["has_text"] else 0
    years = sorted({s["date"][:4] for s in stories if s["date"]})
    nl = [s for s in stories if s["source"] == "newsletter"]
    bl = [s for s in stories if s["source"] == "blog"]
    total_words = sum(s["words"] for s in stories)
    per_year = [(y, [sum(1 for s in nl if s["date"].startswith(y)), sum(1 for s in bl if s["date"].startswith(y))])
                for y in years]
    words_year = [(y, [sum(s["words"] for s in stories if s["date"].startswith(y))]) for y in years]
    wd = collections.Counter(datetime.date.fromisoformat(s["date"][:10]).strftime("%A") for s in stories if s["date"])
    weekdays = [(d, wd[d]) for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]]
    places = collections.Counter(s["place"] for s in stories if s.get("place"))
    with_text = [s for s in stories if s["has_text"] and s["words"] > 50]
    longest = max(with_text, key=lambda s: s["words"])
    shortest = min(with_text, key=lambda s: s["words"])
    chatty = max(stories, key=lambda s: s["comments"])
    dated = sorted(datetime.date.fromisoformat(s["date"][:10]) for s in stories if s["date"])
    gap = max(((b - a).days, a, b) for a, b in zip(dated, dated[1:]))
    busiest_year = max(per_year, key=lambda r: sum(r[1]))
    month = collections.Counter(s["date"][:7] for s in stories if s["date"]).most_common(1)[0]
    vocab = collections.Counter()
    for s in stories:
        if s["has_text"]:
            for w in re.findall(r"[a-z][a-z'’]+", s["text"].lower()):
                w = w.replace("’", "'")
                if w not in STOP and len(w) > 3 and not w.endswith("'s") and not w.endswith("'t"):
                    vocab[w] += 1
    def tile(v, label):
        return f'<div class="tile-stat"><b>{v}</b><span>{label}</span></div>'

    def link(s):
        return f'<a href="{esc(s["url"])}">{esc(s["title"])}</a> ({nice(s["date"])})'

    top_words = vocab.most_common(60)
    mxw = top_words[0][1] if top_words else 1
    cloud = " ".join(f'<span style="font-size:{0.85 + 1.4 * (c / mxw) ** 0.6:.2f}em" title="{c:,} times">{esc(w)}</span>'
                     for w, c in sorted(top_words, key=lambda x: x[0]))
    body = f"""<h1>20 years in numbers</h1>
<p class="intro muted">Every blog post and newsletter issue since {years[0]}, counted. Where a blog post is a copy of
a newsletter issue, it's counted once.</p>
<div class="stat-tiles">
{tile(f"{len(stories):,}", "stories")}
{tile(f"{total_words:,}", "words")}
{tile(len(years), "years of writing")}
{tile(len(places), "places on the map")}
</div>

<h2 class="section">Stories per year</h2>
{svg_bars(per_year, [("Newsletter", NEWSLETTER_GREEN), ("Blog only", BLOG_OCHRE)], label_every=2 if len(years) > 14 else 1)}
{table(["Year", "Newsletter", "Blog only"], [(y, a, b) for y, (a, b) in per_year])}

<h2 class="section">Words per year</h2>
{svg_bars(words_year, [("Words", NEWSLETTER_GREEN)], label_every=2 if len(years) > 14 else 1)}
<p class="muted small">Newsletter word counts come from the Substack export, so issues published since the last export
(and the paid-only one) aren't counted yet.</p>
{table(["Year", "Words"], [(y, f"{v[0]:,}") for y, v in words_year])}

<h2 class="section">Favourite day to publish</h2>
{svg_hbars(weekdays)}

<h2 class="section">Most-written-about places</h2>
{svg_hbars(places.most_common(12))}
<p class="back"><a href="/map/">See them all on the map</a></p>

<h2 class="section">Records</h2>
<ul class="records">
<li><strong>Busiest year:</strong> {busiest_year[0]}, with {sum(busiest_year[1])} stories.</li>
<li><strong>Busiest month:</strong> {MONTHS[int(month[0][5:7]) - 1]} {month[0][:4]}, with {month[1]} stories.</li>
<li><strong>Longest story:</strong> {link(longest)}, {longest["words"]:,} words.</li>
<li><strong>Shortest story:</strong> {link(shortest)}, {shortest["words"]:,} words.</li>
<li><strong>Most comments:</strong> {link(chatty)}, {chatty["comments"]} comments.</li>
<li><strong>Longest silence:</strong> {gap[0]} days, from {nice(gap[1].isoformat())} to {nice(gap[2].isoformat())}.</li>
<li><strong>Average story:</strong> {int(sum(s["words"] for s in with_text) / len(with_text)):,} words, about {max(1, round(sum(s["words"] for s in with_text) / len(with_text) / 230))} minutes' reading.</li>
</ul>

{keyword_section()}

<details class="plain-count"><summary>Plain word count: the 60 words used most often</summary>
<p class="cloud">{cloud}</p>
<p class="muted small">Leaving out little words like "the" and "really". Bigger means more often; hover for the count.
Frequency alone mostly shows what every writer says a lot, which is why the comparison above is more revealing.</p>
</details>"""
    write_if_changed("numbers/index.html", page("20 years in numbers | David Charles",
                                                f"{len(stories):,} stories and {total_words:,} words, counted.",
                                                "/numbers/", body))
    return (f'<a class="stat-tiles home-figures" href="/numbers/" aria-label="20 years in numbers">'
            f'{tile(f"{len(stories):,}", "stories")}{tile(f"{total_words:,}", "words")}'
            f'{tile(len(years), "years of writing")}{tile(len(places), "places on the map")}'
            f'<span class="more">See 20 years in numbers &rarr;</span></a>')


# ---------------------------------------------------------------- Photo wall

def thumb(src, srcset):
    """Pick a ~500px version of an image for the grid."""
    if src.startswith("http"):
        return src     # Substack image addresses are signed, so they can't be resized here
    best = None
    for part in (srcset or "").split(","):
        bits = part.strip().split()
        if len(bits) == 2 and bits[1].endswith("w") and bits[0].startswith("/"):
            w = int(bits[1][:-1])
            if 400 <= w <= 800 and (best is None or abs(w - 500) < abs(best[0] - 500)):
                best = (w, bits[0])
    return best[1] if best else src


GENERIC_IMG = re.compile(r"(logo|avatar|icon|emoji|smiley|button|banner|header|subscribe-card|/twitter/|"
                         r"\.gif$|\.svg$)", re.I)


def photo_candidates(s):
    """Usable photos for a story, best first: the newsletter cover, then decent images in the post."""
    out = []
    if s.get("source") == "newsletter" and s.get("image") and not GENERIC_IMG.search(s["image"]):
        out.append(s["image"])
    for t in re.findall(r"<img\b[^>]*>", s.get("html") or ""):
        src = re.search(r'\ssrc="([^"]+)"', t)
        if not src or GENERIC_IMG.search(src.group(1)):
            continue
        w = re.search(r'\swidth="(\d+)"', t)
        ss = re.search(r'\ssrcset="([^"]+)"', t)
        if w and int(w.group(1)) < 400 and not (ss and re.search(r"\s(?:[5-9]\d\d|\d{4})w", ss.group(1))):
            continue
        out.append(thumb(src.group(1), ss.group(1) if ss else ""))
    img = s.get("image")
    if img and (img.startswith("/") or img.startswith("https://")) and not GENERIC_IMG.search(img):
        out.append(img)
    return out


def img_key(u):
    return re.sub(r"-\d+x\d+(?=\.\w+$)", "", u.split("?")[0])


def common_photos(stories):
    """Images that turn up in more than two stories (stock headers, promo pictures) - not real story photos."""
    c = collections.Counter()
    for s in stories:
        for k in {img_key(u) for u in photo_candidates(s)}:
            c[k] += 1
    return {k for k, n in c.items() if n > 2}


def story_photo(s, common=frozenset()):
    skip = skip_words()
    return next((u for u in photo_candidates(s) if img_key(u) not in common and not any(w in u for w in skip)), None)


def skip_words():
    try:
        return json.load(open("data/timeline.json", encoding="utf-8")).get("skip_photos", [])
    except (OSError, ValueError):
        return []


def build_photos(stories):
    usage = collections.Counter()
    picks = []
    skip = skip_words()
    for s in stories:
        cands = []
        for t in re.findall(r"<img\b[^>]*>", s["html"]):
            src = re.search(r'\ssrc="([^"]+)"', t)
            if not src or re.search(r"(logo|avatar|icon|emoji|smiley|button|banner|header|\.gif$|\.svg$)",
                                    src.group(1), re.I) or any(w in src.group(1) for w in skip):
                continue
            w = re.search(r'\swidth="(\d+)"', t)
            h = re.search(r'\sheight="(\d+)"', t)
            w, h = (int(w.group(1)) if w else 0), (int(h.group(1)) if h else 0)
            if w and w < 400:
                srcset = re.search(r'\ssrcset="([^"]+)"', t)
                if not srcset or not re.search(r"\s(?:[5-9]\d\d|\d{4})w", srcset.group(1)):
                    continue
            ss = re.search(r'\ssrcset="([^"]+)"', t)
            cands.append((src.group(1), ss.group(1) if ss else ""))
        if s["source"] == "newsletter" and s.get("image"):
            cands.insert(0, (s["image"], ""))
        elif not cands and s.get("image") and s["image"].startswith("/"):
            cands.append((s["image"], ""))
        cands = [c for c in cands if not any(w in c[0] for w in skip)]
        if cands:
            usage[re.sub(r"-\d+x\d+(?=\.\w+$)", "", cands[0][0])] += 1
            picks.append((s, cands[0]))
    photos = [(s, c) for s, c in picks if usage[re.sub(r"-\d+x\d+(?=\.\w+$)", "", c[0])] <= 2]
    parts, year = [], None
    for s, (src, srcset) in photos:
        y = s["date"][:4]
        if y != year:
            if year is not None:
                parts.append("</div>")
            parts.append(f'<h2 id="y{y}">{y}</h2><div class="photo-grid">')
            year = y
        parts.append(f'<a href="{esc(s["url"])}" aria-label="{esc(s["title"])}">'
                     f'<img src="{esc(thumb(src, srcset))}" alt="" loading="lazy" decoding="async">'
                     f'<span>{esc(s["title"])}</span></a>')
    if year is not None:
        parts.append("</div>")
    years = sorted({s["date"][:4] for s, _ in photos}, reverse=True)
    jump = chips([(f"#y{y}", y, sum(1 for s, _ in photos if s["date"].startswith(y))) for y in years])
    body = (f'<h1>Photo wall</h1>\n<p class="intro muted">One photo from each of {len(photos):,} stories. Click a '
            f'photo to read the story.</p>\n{jump}\n' + "\n".join(parts))
    write_if_changed("photos/index.html", page("Photo wall | David Charles",
                                               f"{len(photos):,} photos from David Charles's stories.",
                                               "/photos/", body, "/photos/"))
    return len(photos)


# ---------------------------------------------------------------- related reading

def compute_related(stories, n=3):
    """Three most similar stories for each story (TF-IDF over the words, cosine similarity)."""
    docs = []
    for st in stories:
        words = [w for w in re.findall(r"[a-z][a-z'’]+", (st["title"] + " ") * 3 + st["text"].lower())
                 if len(w) > 3 and w.replace("’", "'") not in STOP]
        docs.append(collections.Counter(words))
    df = collections.Counter()
    for d in docs:
        df.update(d.keys())
    N = len(docs)
    vecs = []
    for d in docs:
        total = sum(d.values()) or 1
        v = {w: (c / total) * __import__("math").log(N / df[w]) for w, c in d.items() if 1 < df[w] < N * 0.25}
        top = dict(sorted(v.items(), key=lambda x: -x[1])[:80])
        norm = sum(x * x for x in top.values()) ** 0.5 or 1
        vecs.append({w: x / norm for w, x in top.items()})
    inv = collections.defaultdict(list)
    for i, v in enumerate(vecs):
        for w, x in v.items():
            inv[w].append((i, x))
    for i, v in enumerate(vecs):
        score = collections.Counter()
        for w, x in v.items():
            for j, y in inv[w]:
                if j != i:
                    score[j] += x * y
        title = re.sub(r"\W+", "", stories[i]["title"].lower())
        picks = []
        for j, sc in score.most_common(12):
            if sc < 0.08 or re.sub(r"\W+", "", stories[j]["title"].lower()) == title:
                continue
            picks.append(j)
            if len(picks) == n:
                break
        stories[i]["related"] = picks


# ---------------------------------------------------------------- series

def build_series_data(stories, entries):
    """Series trails. A series collects stories by blog category, by a title pattern, and/or by an explicit
    'include' list of story addresses (blog or newsletter); 'exclude' drops any. Oldest first."""
    conf = json.load(open("data/series.json", encoding="utf-8"))["series"]
    story_of_blog = {s["blog_url"]: s for s in stories if s.get("blog_url")}
    by_url = {s["url"]: s for s in stories}
    common = common_photos(stories)
    posts = [e for e in entries if e["type"] == "post"]
    out = []
    for sr in conf:
        chosen = []
        for e in posts:
            if ((sr.get("category") and any(c["url"] == sr["category"] for c in e.get("cats", [])))
                    or (sr.get("title") and re.search(sr["title"], e["title"], re.I))):
                st = story_of_blog.get(e["url"])
                chosen.append(st or {"title": e["title"], "date": e["date"], "url": e["url"], "blog_url": e["url"],
                                     "source": "blog", "image": e.get("image"), "excerpt": e.get("excerpt", ""),
                                     "html": ""})
        for u in sr.get("include", []):
            st = by_url.get(u) or story_of_blog.get(u)
            if st:
                chosen.append(st)
            else:
                print(f"Note: series {sr['slug']}: no story at {u}")
        drop = set(sr.get("exclude", []))
        chosen = [x for x in chosen if x["url"] not in drop and x.get("blog_url") not in drop
                  and (not sr.get("from") or x["date"] >= sr["from"]) and (not sr.get("to") or x["date"] <= sr["to"])]
        seen, items = set(), []
        for x in sorted(chosen, key=lambda x: (x["date"], x["url"])):
            k = re.sub(r"\W+", "", x["title"].lower())
            if k in seen or x["url"] in seen:
                continue
            seen.update({k, x["url"]})
            items.append({"title": x["title"], "date": x["date"], "url": x["url"], "blog_url": x.get("blog_url"),
                          "source": x["source"], "photo": story_photo(x, common), "excerpt": x.get("excerpt") or ""})
        if len(items) >= 2:
            out.append(dict(sr, items=items))
    return out


def series_box(series_list, blog_url):
    for sr in series_list:
        for i, it in enumerate(sr["items"]):
            if it["blog_url"] == blog_url:
                prev = sr["items"][i - 1] if i > 0 else None
                nxt = sr["items"][i + 1] if i + 1 < len(sr["items"]) else None
                links = ""
                if prev:
                    links += f'<a href="{esc(prev["url"])}">&larr; {esc(prev["title"])}</a>'
                if nxt:
                    links += f'<a class="next" href="{esc(nxt["url"])}">{esc(nxt["title"])} &rarr;</a>'
                data = json.dumps({"slug": sr["slug"], "name": sr["name"], "part": i + 1, "total": len(sr["items"]),
                                   "title": it["title"], "next": nxt["url"] if nxt else "",
                                   "nextTitle": nxt["title"] if nxt else ""}, ensure_ascii=False)
                return (f'<aside class="series-box" data-progress="{esc(data)}"><p><a href="/series/{esc(sr["slug"])}/">'
                        f'{esc(sr["name"])}</a>: part {i + 1} of {len(sr["items"])}</p>'
                        f'<div class="series-links">{links}</div></aside>')
    return ""


def load_books():
    try:
        books = json.load(open("data/books.json", encoding="utf-8"))["books"]
    except (OSError, ValueError):
        return []
    return [b for b in books if os.path.exists(f'books/{b["slug"]}/{b["slug"]}.epub')]


def book_button(series_slug):
    b = next((b for b in load_books() if b["series"] == series_slug and not b.get("draft")), None)
    return f' <a class="button" href="/books/{esc(b["slug"])}/">Read it as a free ebook</a>' if b else ""


def build_books(series_list):
    books = load_books()
    if not books:
        return
    cards = []
    for b in books:
        sr = next((x for x in series_list if x["slug"] == b["series"]), None)
        d = f'books/{b["slug"]}'
        size = lambda f: f'{max(1, round(os.path.getsize(f"{d}/{f}") / 1048576))} MB'
        parts = f'{len(sr["items"])} chapters' if sr else ""
        words = f', about {b["words"]:,} words' if b.get("words") else ""
        body = (f'<p class="meta crumbs"><a href="/books/">Books</a></p>'
                f'<div class="book"><img class="book-cover" src="/{d}/cover-small.jpg" alt="Cover of {esc(b["title"])}" '
                f'width="300" height="424"><div><h1>{esc(b["title"])}</h1><p class="intro"><em>{esc(b["subtitle"])}</em></p>'
                f'<p>{esc(b["description"])}</p><p class="muted">{parts}{words}. Free to read and share.</p>'
                f'<div class="buttons"><a class="button primary" href="/{d}/{b["slug"]}.epub" download>Download ebook '
                f'(EPUB, {size(b["slug"] + ".epub")})</a> <a class="button" href="/{d}/{b["slug"]}.pdf" download>'
                f'PDF to read or print ({size(b["slug"] + ".pdf")})</a></div>'
                f'<p class="muted small">EPUB opens in Apple Books, Google Play Books, Kobo and most e-readers. For '
                f'Kindle, send it to your Kindle with Amazon’s Send to Kindle. Prefer reading online? '
                + (f'<a href="/series/{esc(b["series"])}/">Read it here as a series</a>.' if sr else "")
                + '</p></div></div>'
                '<aside class="newsletter-box"><h2>Liked it?</h2><p>Every Friday I send a short story about '
                'adventure, nature and being human. Join the readers of my newsletter.</p><p><a class="button primary" '
                'href="https://davidcharles.substack.com/subscribe">Subscribe free</a></p></aside>')
        book_schema = {"@context": "https://schema.org", "@type": "Book", "name": b["title"],
                       "alternativeHeadline": b["subtitle"], "description": b["description"],
                       "author": PERSON, "url": f"{SITE}/{d}/", "image": f"{SITE}/{d}/cover.jpg",
                       "inLanguage": "en-GB", "isAccessibleForFree": True, "bookFormat": "https://schema.org/EBook",
                       "offers": {"@type": "Offer", "price": "0", "priceCurrency": "GBP"}}
        write_if_changed(f"{d}/index.html", page(f'{b["title"]}: free ebook | David Charles', b["description"],
                                                 f"/{d}/", body, image=f"/{d}/cover.jpg", noindex=bool(b.get("draft")),
                                                 schema=book_schema))
        if b.get("draft"):
            continue
        cards.append(f'<li><a href="/{d}/"><img src="/{d}/cover-small.jpg" alt="" width="300" height="424" '
                     f'loading="lazy"><h3>{esc(b["title"])}</h3><p>{esc(b["subtitle"])}</p></a></li>')
    body = ('<h1>Books</h1><p class="intro muted">Free ebooks made from the stories on this site, to read on your '
            'phone, e-reader or paper. For my published books, see <a href="/shop/">the shop</a>.</p>'
            f'<ul class="book-grid">{"".join(cards)}</ul>')
    write_if_changed("books/index.html", page("Free ebooks | David Charles",
                                              "Free ebooks by David Charles, made from his travel stories.",
                                              "/books/", body))


TOPICS = [("a", "Adventure", "/category/adventure/"), ("w", "Nature", "/category/nature/"),
          ("h", "How to be human", "/category/how-to-be-human/"), ("p", "Activism", "/category/activism/"),
          ("c", "Writing", "/category/creative-writing/"), ("n", "Newsletter", None)]


def build_picker(stories, entries):
    """The 'Got 5 minutes?' story picker at /random-story/, fed by assets/stories.json."""
    cats_of = {e["url"]: [c["url"] for c in e.get("cats", [])] for e in entries}
    rows = []
    for s in stories:
        words = len((s.get("text") or "").split())
        if words < 80:
            continue
        mins = max(1, round(words / 230))
        cats = cats_of.get(s.get("blog_url"), [])
        topics = [k for k, _, u in TOPICS if u and any(c.startswith(u) for c in cats)]
        if s["source"] == "newsletter":
            topics.append("n")
        rows.append([s["url"], s["title"], mins, s["date"][:4], "".join(topics)])
    rows.sort(key=lambda r: r[0])
    write_if_changed("assets/stories.json", json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n")
    times = "".join(f'<button type="button" class="chip" data-min="{a}" data-max="{b}">{t}</button>'
                    for a, b, t in ((1, 3, "2 minutes"), (4, 6, "5 minutes"), (7, 12, "10 minutes"),
                                    (13, 999, "20 minutes or more")))
    topics = ('<button type="button" class="chip on" data-topic="">Anything</button>'
              + "".join(f'<button type="button" class="chip" data-topic="{k}">{esc(n)}</button>'
                        for k, n, _ in TOPICS))
    body = f"""<h1>Pick me a story</h1>
<p class="intro muted">How long have you got? I’ll find you something from twenty years of stories.</p>
<div class="picker">
<p class="picker-label">Time</p><div class="chips" id="times">{times}</div>
<p class="picker-label">About</p><div class="chips" id="topics">{topics}</div>
<div class="buttons"><button type="button" class="button primary" id="pick">Surprise me</button></div>
<div id="choice" aria-live="polite"></div>
</div>
<script>
(function(){{
  var data=null, mn=1, mx=999, topic="";
  var q=new URLSearchParams(location.search), m=parseInt(q.get("m")||"0",10);
  function load(cb){{ if(data) return cb(); fetch("/assets/stories.json").then(function(r){{return r.json();}})
    .then(function(d){{data=d;cb();}}).catch(function(){{document.getElementById("choice").textContent="Sorry, couldn’t load the stories.";}}); }}
  function mark(group,el){{ group.querySelectorAll(".chip").forEach(function(c){{c.classList.toggle("on",c===el);}}); }}
  function pick(){{ load(function(){{
    var pool=data.filter(function(r){{return r[2]>=mn&&r[2]<=mx&&(!topic||r[4].indexOf(topic)>=0);}});
    var out=document.getElementById("choice");
    if(!pool.length){{ out.innerHTML=""; out.textContent="Nothing quite fits. Try another topic."; return; }}
    var r=pool[Math.floor(Math.random()*pool.length)], a=document.createElement("a");
    a.href=r[0]; a.className="choice-card";
    var t=document.createElement("strong"); t.textContent=r[1];
    var meta=document.createElement("span"); meta.textContent=r[3]+" · "+r[2]+" min read"+(r[4].indexOf("n")>=0?" · newsletter":"");
    a.appendChild(t); a.appendChild(meta);
    out.innerHTML=""; out.appendChild(a);
    var again=document.createElement("button"); again.type="button"; again.className="button"; again.textContent="Another one";
    again.onclick=pick; out.appendChild(again);
    document.getElementById("pick").textContent="Pick again";
  }}); }}
  document.getElementById("times").addEventListener("click",function(e){{ var c=e.target.closest(".chip"); if(!c) return;
    if(c.classList.contains("on")){{ c.classList.remove("on"); mn=1; mx=999; }} else {{ mark(this,c); mn=+c.dataset.min; mx=+c.dataset.max; }} pick(); }});
  document.getElementById("topics").addEventListener("click",function(e){{ var c=e.target.closest(".chip"); if(!c) return;
    mark(this,c); topic=c.dataset.topic; if(document.getElementById("choice").firstChild) pick(); }});
  document.getElementById("pick").addEventListener("click",pick);
  if(m){{ var b=[].find.call(document.querySelectorAll("#times .chip"),function(c){{return m>=+c.dataset.min&&m<=+c.dataset.max;}});
    if(b) b.click(); }}
}})();
</script>"""
    write_if_changed("random-story/index.html", page("Pick me a story | David Charles",
                                                     "Got five minutes? A story picker for twenty years of writing.",
                                                     "/random-story/", body))
    return len(rows)


def build_series_pages(series_list):
    def pic(it, cls=""):
        if it.get("photo"):
            return f'<img{cls} src="{esc(it["photo"])}" alt="" loading="lazy" decoding="async">'
        colour = TILE_COLOURS[sum(map(ord, it["title"])) % len(TILE_COLOURS)]
        return f'<span class="ph" style="background:{colour}" aria-hidden="true"></span>'

    for sr in series_list:
        rows = "".join(
            f'<li><a href="{esc(it["url"])}">{pic(it)}<div><span class="num">Part {i + 1}</span>'
            f'<h3>{esc(it["title"])}</h3>'
            f'<time datetime="{esc(it["date"])}">{esc(nice(it["date"]))}'
            f'{" &middot; newsletter" if it["source"] == "newsletter" else ""}</time>'
            + (f'<p>{esc(it["excerpt"][:160].rsplit(" ", 1)[0] + "…" if len(it["excerpt"]) > 160 else it["excerpt"])}</p>'
               if it["excerpt"] else "")
            + '</div></a></li>'
            for i, it in enumerate(sr["items"]))
        first = sr["items"][0]
        cover = ({"photo": sr["cover"]} if sr.get("cover")
                 else next((it for it in sr["items"] if it.get("photo")), None))
        hero = (f'<figure class="series-hero"><img src="{esc(cover["photo"])}" alt=""></figure>' if cover else "")
        years = f'{first["date"][:4]}–{sr["items"][-1]["date"][:4]}' if first["date"][:4] != sr["items"][-1]["date"][:4] \
            else first["date"][:4]
        body = (f'<p class="meta crumbs"><a href="/series/">Series</a></p>{hero}<h1>{esc(sr["name"])}</h1>\n'
                f'<p class="intro">{esc(sr["description"])}</p>\n<p class="intro muted">{len(sr["items"])} parts, '
                f'{years}, in order.</p>\n<div class="buttons"><a class="button primary" href="{esc(first["url"])}">'
                f'Start at part 1</a>{book_button(sr["slug"])}</div>\n'
                f'<p class="continue" data-series="{esc(sr["slug"])}" hidden></p>\n<ol class="series-cards">{rows}</ol>')
        write_if_changed(f'series/{sr["slug"]}/index.html', page(f'{sr["name"]} | David Charles', sr["description"],
                                                                 f'/series/{sr["slug"]}/', body,
                                                                 image=cover["photo"] if cover else None))
    cards = []
    for sr in series_list:
        cover = (dict(sr["items"][0], photo=sr["cover"]) if sr.get("cover")
                 else next((it for it in sr["items"] if it.get("photo")), sr["items"][0]))
        cards.append(
            f'<li><a href="/series/{esc(sr["slug"])}/">{pic(cover)}<div><h3>{esc(sr["name"])}</h3>'
            f'<p>{esc(sr["description"])}</p><span class="muted">{len(sr["items"])} parts &middot; '
            f'{sr["items"][0]["date"][:4]}</span></div></a></li>')
    body = ('<h1>Series</h1>\n<p class="intro muted">Stories told in several parts, from bike rides to book '
            f'clubs. Each one reads like a short book.</p>\n<ul class="series-covers">{"".join(cards)}</ul>')
    write_if_changed("series/index.html", page("Series | David Charles", "Stories by David Charles told in parts.",
                                               "/series/", body, "/series/"))


# ---------------------------------------------------------------- Start here

def build_editor_setup():
    """/edit/: switches on the in-place post editor (assets/editor.js) in this browser. Not linked or indexed."""
    body = """<h1>Site editor</h1>
<p>This turns on an <strong>Edit</strong> button on every post, in this browser only. Tap it, change the words,
press Save, and the website updates in about three minutes. Every save is recorded on GitHub, so nothing is
ever lost.</p>
<h2 class="section">1. Make a key on GitHub (once)</h2>
<ol>
<li>Open <a href="https://github.com/settings/personal-access-tokens/new">GitHub's new fine-grained token page</a>
(signed in as dcisbusy).</li>
<li><strong>Token name:</strong> Site editor. <strong>Expiration:</strong> a year (GitHub will remind you).</li>
<li><strong>Repository access:</strong> Only select repositories &rarr; <em>dcisbusy/davidcharlesinfo</em>.</li>
<li><strong>Permissions &rarr; Repository permissions &rarr; Contents:</strong> Read and write. Leave everything else.</li>
<li>Press <strong>Generate token</strong> and copy it (it starts <code>github_pat_</code>). GitHub shows it only once.</li>
</ol>
<h2 class="section">2. Paste it here (once per phone or computer)</h2>
<form id="ed-form" autocomplete="off">
<p><label for="ed-token">Token</label><br>
<input id="ed-token" type="password" spellcheck="false" autocapitalize="off" style="width:100%;max-width:32em;font:15px/1.4 var(--ui);padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)"></p>
<p class="buttons"><button class="button primary" type="submit">Save and test</button>
<button class="button" type="button" id="ed-remove">Turn the editor off here</button></p>
<p id="ed-status" role="status" class="muted"></p>
</form>
<h2 class="section">3. Edit</h2>
<p>Open any post on the site and tap <strong>Edit</strong> at the bottom right. Bold, italic and links are on the
toolbar; Undo and Cancel are there if something goes wrong. Titles, dates and photos aren't editable here: ask Claude
for those.</p>
<p class="muted small">The key stays in this browser's storage. If your phone is lost, delete the token on GitHub
(Settings &rarr; Developer settings &rarr; Fine-grained tokens) and it stops working at once.</p>
<script>
(function(){
  var st=document.getElementById('ed-status'), inp=document.getElementById('ed-token');
  function have(){try{return localStorage.getItem('dc-edit-token');}catch(e){return null;}}
  st.textContent=have()?'The editor is on in this browser.':'The editor is off in this browser.';
  document.getElementById('ed-form').addEventListener('submit',function(e){
    e.preventDefault(); var t=inp.value.trim(); if(!t){st.textContent='Paste the token first.';return;}
    st.textContent='Checking with GitHub\u2026';
    fetch('https://api.github.com/repos/dcisbusy/davidcharlesinfo',{headers:{'Authorization':'Bearer '+t,'Accept':'application/vnd.github+json'}})
      .then(function(r){return r.json().then(function(j){return [r.status,j];});})
      .then(function(x){
        if(x[0]!==200){st.textContent='GitHub didn\u2019t accept that token ('+x[0]+'). Check it was copied whole and gives access to davidcharlesinfo.';return;}
        if(x[1].permissions&&!x[1].permissions.push){st.textContent='That token can read the site but not save to it: set Contents to \u201cRead and write\u201d.';return;}
        try{localStorage.setItem('dc-edit-token',t);}catch(e){st.textContent='This browser won\u2019t store the token (private browsing?).';return;}
        inp.value=''; st.textContent='Done: the editor is on in this browser. Open any post and tap Edit.';
      }).catch(function(){st.textContent='Couldn\u2019t reach GitHub. Check your connection.';});
  });
  document.getElementById('ed-remove').addEventListener('click',function(){
    try{localStorage.removeItem('dc-edit-token');}catch(e){}
    st.textContent='The editor is off in this browser. (The token still exists on GitHub until you delete it there.)';
  });
})();
</script>"""
    write_if_changed("edit/index.html", page("Site editor | David Charles", "Turn on the in-place post editor.",
                                             "/edit/", body, noindex=True))


def build_work_with_me():
    """/work-with-me/ from data/work-with-me.html. Hidden (noindex, unlinked) while its first comment says DRAFT."""
    src = read("data/work-with-me.html")
    if not src:
        return
    draft = bool(re.match(r"\s*<!--[^>]*\bDRAFT\b", src))
    body = re.sub(r"<!--.*?-->\s*", "", src, flags=re.S).strip()
    write_if_changed("work-with-me/index.html", page(
        "Work with me | David Charles",
        "Nature connection, wilderness therapy, talks, writing, editing and comedy writing with David Charles.",
        "/work-with-me/", body, noindex=draft))
    return draft


def build_timeline(stories, series_list):
    """/timeline/: twenty years, a year at a time. Milestones from data/timeline.json, plus series,
    yearly story counts and a few photographs chosen from each year's stories."""
    try:
        tl = json.load(open("data/timeline.json", encoding="utf-8"))
    except (OSError, ValueError):
        tl = {}
    miles, skip = tl.get("milestones", []), tl.get("skip_photos", [])
    common = common_photos(stories)
    try:
        picks = {it["url"] for th in json.load(open("data/start-here.json", encoding="utf-8")).get("themes", [])
                 for it in th.get("items", [])}
    except (OSError, ValueError, AttributeError):
        picks = set()
    firsts = {sr["items"][0]["url"] for sr in series_list}
    years = {}
    for st in stories:
        y = st["date"][:4]
        if y.isdigit():
            years.setdefault(y, []).append(st)
    for m in miles:
        years.setdefault(m["date"][:4], [])
    starts = {}
    for sr in series_list:
        starts.setdefault(sr["items"][0]["date"][:4], []).append(sr)

    out = []
    for y in sorted(years):
        ys = years[y]
        nb = sum(1 for x in ys if x["source"] == "blog")
        nn = sum(1 for x in ys if x["source"] == "newsletter")
        counts = " &middot; ".join(t for t in (f"{nb} blog post{'s' * (nb != 1)}" if nb else "",
                                                f"{nn} newsletter issue{'s' * (nn != 1)}" if nn else "") if t)
        events = []
        for m in sorted((m for m in miles if m["date"][:4] == y), key=lambda m: m["date"]):
            t = esc(m["title"])
            if m.get("url"):
                t = f'<a href="{esc(m["url"])}">{t}</a>'
            events.append((m["date"], f'<li class="milestone"><strong>{t}</strong> {esc(m.get("text", ""))}</li>'))
        for sr in starts.get(y, []):
            events.append((sr["items"][0]["date"],
                           f'<li class="series-start"><strong><a href="/series/{esc(sr["slug"])}/">{esc(sr["name"])}</a>'
                           f'</strong> {esc(sr["description"])} <span class="muted">{len(sr["items"])} parts</span></li>'))
        events.sort(key=lambda e: e[0])
        # up to three photos: series openers and Start here picks first, then the longest stories
        cands = sorted(ys, key=lambda x: (x["url"] not in firsts and x["url"] not in picks,
                                          -len((x.get("text") or "").split())))
        photos, used = [], set()
        for x in cands:
            ph = next((u for u in photo_candidates(x) if img_key(u) not in common
                       and not re.search(r"\.png($|\?)|%2F[^/]*\.png|/image/youtube/", u, re.I)
                       and not any(w in u for w in skip)), None)
            if ph and img_key(ph) not in used:
                used.add(img_key(ph))
                photos.append(f'<a href="{esc(x["url"])}" title="{esc(x["title"])}"><img src="{esc(ph)}" alt="" '
                              f'loading="lazy" decoding="async"><span>{esc(x["title"])}</span></a>')
            if len(photos) == 3:
                break
        if not (events or photos or counts):
            continue
        out.append(f'<section class="tl-year" id="y{y}"><h2>'
                   + (f'<a href="/{y}/">{y}</a>' if os.path.exists(f"{y}/index.html") else y) + '</h2>'
                   + (f'<p class="muted tl-count">{counts}</p>' if counts else "")
                   + (f'<ul class="tl-events">{"".join(e for _, e in events)}</ul>' if events else "")
                   + (f'<div class="tl-photos">{"".join(photos)}</div>' if photos else "")
                   + "</section>")
    first, last = (min(years), max(years)) if years else ("", "")
    jump = " ".join(f'<a href="#y{y}">{y[2:] if i else y}</a>' for i, y in enumerate(sorted(years)))
    body = (f'<h1>Twenty years</h1><p class="intro muted">{first} to {last}, a year at a time: the journeys, the '
            f'projects, the turning points, and the stories written along the way.</p>'
            f'<p class="tl-jump">{jump}</p><div class="timeline">{"".join(out)}</div>')
    write_if_changed("timeline/index.html", page("Twenty years: a timeline | David Charles",
                                                 "Twenty years of journeys, projects and stories by David Charles.",
                                                 "/timeline/", body))


def build_start_here(stories, entries, series_list):
    """The Start here page: a photo doorway, one tile per theme, then each theme's picks as photo cards.
    Words come from data/start-here.json; photos from each story (or an item's own "photo")."""
    conf = json.load(open("data/start-here.json", encoding="utf-8"))
    by_blog = {s["blog_url"]: s for s in stories if s.get("blog_url")}
    by_url = {s["url"]: s for s in stories}
    entry = {e["url"]: e for e in entries}
    slugs = {f'/series/{sr["slug"]}/': sr for sr in series_list}
    common = common_photos(stories)

    def pic(photo, title):
        if photo:
            return f'<img src="{esc(photo)}" alt="" loading="lazy" decoding="async">'
        colour = TILE_COLOURS[sum(map(ord, title)) % len(TILE_COLOURS)]
        return f'<span class="ph" style="background:{colour}" aria-hidden="true"></span>'

    themes = []
    for th in conf["themes"]:
        cards = []
        for it in th["items"]:
            u = it["url"]
            st = by_blog.get(u) or by_url.get(u)
            if u in slugs:
                sr = slugs[u]
                cover = sr.get("cover") or next((x["photo"] for x in sr["items"] if x.get("photo")), None)
                title, url, date, photo = sr["name"], u, sr["items"][0]["date"], it.get("photo") or cover
                meta = f'Series &middot; {len(sr["items"])} parts'
            elif st:
                title, url, date = st["title"], st["url"], st["date"]
                photo = it.get("photo") or story_photo(st, common)
                text = st.get("text") or ""
                if st["source"] != "newsletter":                    # blog stories: count the whole post
                    m = sys.modules["build"].CONTENT_RE.search(read(file_for(st["url"])) or "")
                    text = re.sub(r"<[^>]+>", " ", m.group(1)) if m else text
                words = len(re.findall(r"[A-Za-z\u00C0-\u024F'\u2019-]+", text))
                meta = (f"{max(1, round(words / 230))} min read" if words > 150 else "") + \
                    (" &middot; newsletter" if st["source"] == "newsletter" else "")
            elif u in entry:
                title, url, date, photo, meta = entry[u]["title"], u, entry[u]["date"], it.get("photo"), ""
            else:
                print("Start here: can't find", u)
                continue
            cards.append({"title": title, "url": url, "date": date, "photo": photo, "meta": meta, "note": it["note"]})
        if cards:
            themes.append((th, cards))

    def anchor(name):
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    hero = conf.get("hero")
    doors = "".join(
        f'<li><a href="#{anchor(th["name"])}">{pic(th.get("photo") or next((c["photo"] for c in cards if c["photo"]), None), th["name"])}'
        f'<span class="label">{esc(th["name"])}<small>{len(cards)} {"story" if len(cards) == 1 else "stories"}</small></span></a></li>'
        for th, cards in themes)
    sections = []
    for th, cards in themes:
        lis = "".join(
            f'<li><a href="{esc(c["url"])}">{pic(c["photo"], c["title"])}<div><h3>{esc(c["title"])}</h3>'
            f'<p>{esc(c["note"])}</p><span class="meta">{esc(c["date"][:4])}'
            f'{" &middot; " + c["meta"] if c["meta"] else ""}</span></div></a></li>' for c in cards)
        sections.append(f'<h2 class="section" id="{anchor(th["name"])}">{esc(th["name"])}</h2>\n'
                        f'<ul class="sh-picks">{lis}</ul>')
    explore = [("/series/", "Series"), ("/map/", "Adventure map"), ("/trees/", "Tree map"), ("/timeline/", "Timeline"),
               ("/random-story/", "Pick me a story"), ("/books/", "Free ebooks")]
    tiles = "".join(f'<li><a href="{u}"><img src="/cards/{u.strip("/")}.jpg" alt="{esc(t)}" loading="lazy" '
                    f'decoding="async" width="1200" height="630"></a></li>'
                    for u, t in explore if os.path.exists(f'cards/{u.strip("/")}.jpg'))
    body = ((f'<header class="sh-hero"><img src="{esc(hero)}" alt="" fetchpriority="high">' if hero
             else '<header class="sh-hero plain">') +
            f'<div><h1>Start here</h1><p>{esc(conf["intro"])}</p></div></header>\n'
            f'<ul class="sh-doors">{doors}</ul>\n'
            '<p class="quick-pick">Got <a href="/random-story/?m=2">2 minutes</a>, <a href="/random-story/?m=5">5</a>, '
            '<a href="/random-story/?m=10">10</a> or <a href="/random-story/?m=20">20</a>? '
            '<a href="/random-story/">Pick me a story</a></p>\n'
            + "\n".join(sections) +
            '\n<h2 class="section">Then&hellip;</h2>\n<p>Follow one of the <a href="/series/">series</a>, wander the '
            '<a href="/map/">map</a>, <a href="/search/">search</a> for anything, or let me pick a '
            '<a href="/random-story/">random story</a>.</p>\n'
            f'<ul class="sh-explore">{tiles}</ul>\n'
            f'<div class="buttons"><a class="button primary" href="{SUBSTACK}/subscribe">Subscribe on Substack</a></div>')
    write_if_changed("start-here/index.html", page("Start here | David Charles",
                                                   "The best places to begin reading David Charles.", "/start-here/",
                                                   body, "/start-here/"))


# ---------------------------------------------------------------- search

def search_records(stories, entries):
    recs = []
    for s in stories:
        content = s["text"] if not s.get("paid") else f'{s["title"]}. {s.get("excerpt", "")}'
        recs.append({"url": s["url"], "title": s["title"], "date": s["date"], "content": content,
                     "type": "Newsletter" if s["source"] == "newsletter" else "Blog"})
    for e in entries:
        if e["type"] == "page" and e.get("listed", True):
            h = read(file_for(e["url"])) or ""
            m = re.search(r"<!--content:start-->(.*?)<!--content:end-->", h, re.S)
            recs.append({"url": e["url"], "title": e["title"], "date": "", "content": plain(m.group(1) if m else ""),
                         "type": "Page"})
    with open("_search_records.json", "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False)
    body = ('<h1>Search</h1>\n<p class="intro muted">Search every newsletter issue, blog post and page.</p>\n'
            '<div id="search"></div>\n<link rel="stylesheet" href="/pagefind/pagefind-ui.css">\n'
            '<script src="/pagefind/pagefind-ui.js"></script>\n'
            '<script>window.addEventListener("DOMContentLoaded",function(){var ui=new PagefindUI({element:"#search",'
            'showSubResults:false,showImages:false,translations:{placeholder:"Search 20 years of '
            'writing"}});var q=new URLSearchParams(location.search).get("q");if(q){ui.triggerSearch(q);}});</script>')
    write_if_changed("search/index.html", page("Search | David Charles", "Search David Charles's writing.", "/search/",
                                               body, "/search/"))


# ---------------------------------------------------------------- run all

def prepare(issues, entries):
    stories, over = load_stories(issues, entries)
    mentions = find_places(stories, over)
    compute_related(stories)
    series_list = build_series_data(stories, entries)
    by_blog = {s["blog_url"]: s for s in stories if s.get("blog_url")}
    per_post = {}
    for s in stories:
        if s.get("blog_url"):
            rel = [{"title": stories[j]["title"], "url": stories[j]["url"], "date": stories[j]["date"],
                    "source": stories[j]["source"]} for j in s.get("related", [])]
            per_post[s["blog_url"]] = {"related": rel, "series": series_box(series_list, s["blog_url"]),
                                       "newsletter": s["url"] if s["source"] == "newsletter" else None}
    minutes = {}
    for s in stories:
        if s["source"] == "newsletter" and s["has_text"] and not s.get("paid"):
            words = len(re.findall(r"[A-Za-z\u00C0-\u024F'\u2019-]+", s["text"]))
            minutes[s["url"]] = max(1, round(words / 230))
    return {"stories": stories, "mentions": mentions, "series": series_list, "per_post": per_post, "by_blog": by_blog,
            "minutes": minutes}


def build_feed(stories, n=40):
    from email.utils import format_datetime
    items = []
    for s in [s for s in stories if s["date"]][:n]:
        d = datetime.datetime.fromisoformat(s["date"][:10]).replace(hour=12, tzinfo=datetime.timezone.utc)
        url = s["url"] if s["url"].startswith("http") else SITE + s["url"]
        items.append(f"<item><title>{esc(s['title'])}</title><link>{esc(url)}</link><guid>{esc(url)}</guid>"
                     f"<pubDate>{format_datetime(d)}</pubDate><description>{esc(s.get('excerpt') or '')}</description></item>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
           f'<title>David Charles</title><link>{SITE}/</link>'
           '<description>Newsletter issues and stories by David Charles.</description><language>en-gb</language>'
           f'<atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>' + "".join(items) + "</channel></rss>\n")
    write_if_changed("feed.xml", xml)


def build_pages(ctx, entries):
    stories = ctx["stories"]
    build_feed(stories)
    build_map(stories)
    otd = build_on_this_day(stories)
    figures = build_numbers(stories, ctx["mentions"])
    n = build_photos(stories)
    build_series_pages(ctx["series"])
    build_books(ctx["series"])
    build_picker(stories, entries)
    build_timeline(stories, ctx["series"])
    build_work_with_me()
    build_editor_setup()
    build_start_here(stories, entries, ctx["series"])
    search_records(stories, entries)
    print(f"Map: {sum(1 for s in stories if s.get('place'))} stories placed; photo wall: {n} photos; "
          f"{len(ctx['series'])} series")
    return figures + otd
