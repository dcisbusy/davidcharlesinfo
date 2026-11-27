"""Follow the roads for each ride in data/rides/*.json.

For every day, the bike legs between the places David passed are routed along real roads and paths with the
FOSSGIS bike router (routing.openstreetmap.de, OpenStreetMap data); ferry legs stay straight lines. The result
goes to data/rides/<slug>.route.json, which build_rides() in scripts/extras.py draws instead of straight lines.
It also prints each day's routed miles beside the miles David logged, to spot a stop in the wrong place.
Run by the "Ride routes" workflow (the router can't be reached from everywhere)."""
import glob, json, math, sys, time, urllib.error, urllib.request

ROUTER = "https://routing.openstreetmap.de/routed-bike/route/v1/driving/"
HEADERS = {"User-Agent": "davidcharles.info ride map (https://davidcharles.info/rides/)"}


def route(a, b, name=""):
    """Road geometry from a to b ([lat, lon] each) and its length in miles; a straight line if the router fails.
    Ferries are left out where the router allows it (exclude=ferry): the ride data says which crossings David took."""
    base = f"{ROUTER}{a[1]},{a[0]};{b[1]},{b[0]}?overview=full&geometries=geojson"
    tries = ([base + "&exclude=ferry"] if EXCLUDE[0] else []) + [base, base, base]
    for attempt, url in enumerate(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
                j = json.load(r)
            if j.get("code") == "Ok" and j["routes"]:
                rt = j["routes"][0]
                miles = rt["distance"] / 1609.344
                if miles > max(20, 3 * crow(a, b)):   # a wild detour (a ferry, or a road missing from the map)
                    print("  DETOUR, straight line instead:", name, round(miles), "miles routed", file=sys.stderr)
                    return [a, b], crow(a, b)
                return [[round(y, 5), round(x, 5)] for x, y in rt["geometry"]["coordinates"]], miles
        except urllib.error.HTTPError as e:
            if "exclude" in url and e.code == 400:
                EXCLUDE[0] = False      # this router doesn't offer it: stop asking
                print("  router has no ferry exclusion; using plain routes", file=sys.stderr)
                continue
            print("  retry", attempt + 1, name, e, file=sys.stderr)
            time.sleep(5)
        except Exception as e:   # network hiccup or router busy: wait and try again
            print("  retry", attempt + 1, name, e, file=sys.stderr)
            time.sleep(5)
    print("  STRAIGHT LINE (router failed):", name, a, b, file=sys.stderr)
    return [a, b], crow(a, b)


EXCLUDE = [True]


def crow(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def simplify(pts, tol=0.0002):
    """Douglas-Peucker on lat/lon (about 20 m), so the page stays light."""
    if len(pts) < 3:
        return pts
    def dist(p, a, b):
        if a == b:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = max(0, min(1, ((p[0]-a[0])*(b[0]-a[0]) + (p[1]-a[1])*(b[1]-a[1])) / ((b[0]-a[0])**2 + (b[1]-a[1])**2)))
        return math.hypot(p[0] - a[0] - t*(b[0]-a[0]), p[1] - a[1] - t*(b[1]-a[1]))
    keep, stack = {0, len(pts) - 1}, [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        k, dmax = None, tol
        for n in range(i + 1, j):
            d = dist(pts[n], pts[i], pts[j])
            if d > dmax:
                k, dmax = n, d
        if k is not None:
            keep.add(k)
            stack += [(i, k), (k, j)]
    return [pts[n] for n in sorted(keep)]


for f in sorted(glob.glob("data/rides/*.json")):
    if f.endswith(".route.json"):
        continue
    ride = json.load(open(f, encoding="utf-8"))
    out = {"_note": "Made by scripts/ride_routes.py from " + f + ". Don't edit by hand.", "days": {}, "miles": {}}
    here = [ride["start"]["lat"], ride["start"]["lon"]]
    print("==", ride["title"])
    for d in ride["days"]:
        if d.get("offroute"):
            continue
        pts = [[l[0], l[1], l[2], l[3] if len(l) > 3 else ""] for l in d.get("legs", [])] + \
              [[d["lat"], d["lon"], d.get("last", "bike"), d["stop"]]]
        parts, miles = [], 0.0
        for p in pts:
            nxt = [p[0], p[1]]
            if nxt == here:
                continue
            if p[2] != "bike":   # ferries, trains, louages and taxis: a straight line, drawn in its own style
                parts.append([p[2], [here, nxt]])
            else:
                geo, m = route(here, nxt, f"day {d['day']} to {p[3]}")
                miles += m
                time.sleep(1)    # be gentle with a free service
                if parts and parts[-1][0] == "bike":
                    parts[-1][1] += geo[1:]
                else:
                    parts.append(["bike", geo])
            here = nxt
        out["days"][str(d["day"])] = [[m, simplify(g)] for m, g in parts]
        out["miles"][str(d["day"])] = round(miles, 1)
        flag = "  <-- check" if d["miles"] and abs(miles - d["miles"]) > max(15, 0.25 * d["miles"]) else ""
        print(f"Day {d['day']:>2} {d['stop'][:32]:32} logged {d['miles']:6.1f}  routed {miles:6.1f}{flag}")
    with open(f.replace(".json", ".route.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
        fh.write("\n")
