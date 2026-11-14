"""Build the data for the local tree map (/trees/) from the London Datastore.

Runs on GitHub ("Update tree data" workflow), because the sandbox can't reach the Datastore.
Downloads the London Public Realm Trees CSV (about 1.1 million trees), keeps the trees inside
AREA (Crystal Palace, Upper and South Norwood, Beckenham, Penge, Sydenham, Forest Hill, Dulwich)
and writes two small files the page loads:

  trees/trees-data.txt    one tree per line: id|lat|lon|species|place|borough|climate|height|canopy|girth
                          (species, place and borough are numbers pointing into the lookup file)
  trees/trees-lookup.json the species, place-type and borough names

Licence: Open Government Licence v3, Greater London Authority and the borough councils.
"""
import collections
import csv
import io
import json
import os
import re
import sys
import urllib.request

# south, west, north, east
AREA = (51.383, -0.125, 51.458, 0.035)
CKAN = "https://ckan.publishing.service.gov.uk/api/3/action/"
RESOURCE = "59908e1d-a2c8-4ff8-b6ff-c94ef3ff51b1"      # Public_Realm_tree_list (May 2025)
DATASET = "london-public-realm-trees1"
UA = {"User-Agent": "davidcharles.info tree map (github.com/dcisbusy/davidcharlesinfo)"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600)


def csv_url():
    if os.environ.get("TREES_CSV_URL"):
        return os.environ["TREES_CSV_URL"]
    try:
        r = json.load(get(CKAN + "resource_show?id=" + RESOURCE))["result"]
        if r.get("url"):
            return r["url"]
    except Exception as e:
        print("resource_show failed:", e)
    pkg = json.load(get(CKAN + "package_show?id=" + DATASET))["result"]
    for r in pkg["resources"]:
        print("resource:", r.get("name"), r.get("format"), r.get("url"))
    csvs = [r for r in pkg["resources"] if (r.get("url") or "").lower().endswith(".csv")
            or (r.get("format") or "").lower() == "csv"]
    if not csvs:
        sys.exit("No CSV resource found")
    return csvs[0]["url"]


def pick(header, *patterns, avoid=()):
    low = [h.lower().strip() for h in header]
    for p in patterns:
        for i, h in enumerate(low):
            if re.search(p, h) and not any(re.search(a, h) for a in avoid):
                return i
    return None


def place_type(v):
    v = (v or "").lower()
    if re.search(r"highway|street|road|pavement|verge", v):
        return "Highways"
    if re.search(r"park|open space|green|wood|common|cemetery|recreation", v):
        return "Parks"
    if re.search(r"housing|estate|residential", v):
        return "Housing"
    return "Other"


def num(v):
    v = (v or "").strip()
    try:
        f = float(v)
    except ValueError:
        return ""
    return "" if f <= 0 else (str(int(f)) if f == int(f) else f"{f:g}")


def main():
    url = csv_url()
    print("Downloading", url)
    raw = get(url).read()
    print(f"{len(raw) / 1e6:.1f} MB")
    text = raw.decode("utf-8-sig", errors="replace")
    rows = csv.reader(io.StringIO(text))
    header = next(rows)
    print("Columns:", header)
    col = {
        "id": pick(header, r"^(gla_)?tree_?id$", r"uniqueid", r"^objectid$", r"\bid\b"),
        "lat": pick(header, r"^lat", r"latitude"),
        "lon": pick(header, r"^lon", r"^lng", r"longitude"),
        "species": pick(header, r"common", r"species_?name", r"species", avoid=(r"latin", r"botanical", r"scien")),
        "latin": pick(header, r"latin", r"botanical", r"scien", r"taxon"),
        "borough": pick(header, r"borough"),
        "place": pick(header, r"location", r"land_?use", r"site_?type", r"asset_?type", r"ownership"),
        "climate": pick(header, r"climate"),
        "height": pick(header, r"height"),
        "canopy": pick(header, r"canopy", r"spread", r"crown"),
        "girth": pick(header, r"girth", r"dbh", r"diameter", r"stem"),
    }
    print("Using:", {k: (header[v] if v is not None else None) for k, v in col.items()})
    if col["lat"] is None or col["lon"] is None or col["species"] is None:
        sys.exit("Couldn't find latitude, longitude and species columns")
    s, w, n, e = AREA
    species, boroughs, places = {}, {}, ["Highways", "Housing", "Other", "Parks"]
    out, total, by_borough, raw_places = [], 0, collections.Counter(), collections.Counter()

    def idx(table, v):
        if v not in table:
            table[v] = len(table)
        return table[v]

    def cell(r, k):
        i = col[k]
        return r[i].strip() if i is not None and i < len(r) else ""

    for r in rows:
        total += 1
        try:
            lat, lon = float(cell(r, "lat")), float(cell(r, "lon"))
        except ValueError:
            continue
        if not (s <= lat <= n and w <= lon <= e):
            continue
        name = cell(r, "species") or cell(r, "latin") or "Unknown tree"
        name = name[:1].upper() + name[1:]
        borough = cell(r, "borough") or "Unknown"
        raw_places[cell(r, "place")] += 1
        by_borough[borough] += 1
        clim = cell(r, "climate")
        out.append("|".join([cell(r, "id") or str(total), f"{lat:.5f}", f"{lon:.5f}",
                             str(idx(species, name)), str(places.index(place_type(cell(r, "place")))),
                             str(idx(boroughs, borough)), clim if len(clim) < 20 else "",
                             num(cell(r, "height")), num(cell(r, "canopy")), num(cell(r, "girth"))]))
    print(f"{total} trees in London, {len(out)} in the area")
    print("By borough:", dict(by_borough.most_common()))
    print("Place values:", dict(raw_places.most_common(25)))
    if len(out) < 1000:
        sys.exit("Suspiciously few trees: not writing")
    os.makedirs("trees", exist_ok=True)
    with open("trees/trees-data.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    with open("trees/trees-lookup.json", "w", encoding="utf-8") as f:
        json.dump({"species": list(species), "locations": places, "boroughs": list(boroughs),
                   "source": url, "area": AREA}, f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
