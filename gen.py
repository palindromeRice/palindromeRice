"""Render the profile README charts as animated SVGs into assets/.

Needs GH_TOKEN for the profile owner. With private repo read access the charts
include private work; only aggregate counts are drawn, never repo names.
"""
import datetime as dt
import functools
import json
import math
import os
import urllib.request
from collections import Counter

STYLE = """
<style>
  text { font-family: 'Cormorant Garamond', 'EB Garamond', Georgia, serif; fill: #3d3d3d; }
  .muted { fill: #9b8a76; } .title { font-size: 20px; } .lbl { font-size: 13px; } .val { font-size: 14px; }
  .big { font-size: 34px; fill: #043976; } .bar { fill: #043976; } .axis { stroke: #e2ddd6; }
  .grow-y { transform-box: fill-box; transform-origin: bottom; animation: gy .9s cubic-bezier(.2,.8,.2,1) both; }
  .grow-x { transform-box: fill-box; transform-origin: left; animation: gx .9s cubic-bezier(.2,.8,.2,1) both; }
  .rise { animation: rise .7s cubic-bezier(.2,.8,.2,1) both; }
  .fade { animation: fade .6s ease-out both; }
  .cell { fill: #043976; } .empty { fill: #ebe7e1; }
  .l1 { opacity: .3; } .l2 { opacity: .55; } .l3 { opacity: .8; } .l4 { opacity: 1; }
  .pop { transform-box: fill-box; transform-origin: center; animation: pop .4s ease-out both; }
  .area { fill: #043976; opacity: .12; } .line { fill: none; stroke: #043976; stroke-width: 2; }
  .draw { stroke-dasharray: 1; animation: draw 1.8s ease-out both; }
  .spoke { stroke: #043976; stroke-width: 7; stroke-linecap: round; stroke-dasharray: 1; animation: draw .8s ease-out both; }
  .ring { stroke: #e2ddd6; fill: none; }
  @keyframes pop { from { opacity: 0; transform: scale(.3); } }
  @keyframes draw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
  @keyframes gy { from { transform: scaleY(0); } }
  @keyframes gx { from { transform: scaleX(0); } }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } }
  @keyframes fade { from { opacity: 0; } }
  @media (prefers-color-scheme: dark) {
    text { fill: #e7e9ee; } .muted { fill: #b8a68f; } .axis { stroke: #30363d; }
    .bar, .big, .cell { fill: #8fb4e8; } .empty { fill: #1f242c; } .ring { stroke: #30363d; }
    .area { fill: #8fb4e8; } .line, .spoke { stroke: #8fb4e8; }
  }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; } }
</style>"""

QUERY = """{ viewer {
  id followers { totalCount }
  repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
    totalCount nodes { stargazerCount languages(first: 10) { edges { size node { name } } } } }
  contributionsCollection {
    totalCommitContributions totalPullRequestContributions totalIssueContributions
    contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } } }
} }"""


def svg(w, h, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{label}">{STYLE}{body}</svg>\n')


def delay(i, step=0.06):
    return f'style="animation-delay:{i * step:.2f}s"'


COMMITS = """{ viewer { repositories(first: 100, ownerAffiliations: OWNER, isFork: false) { nodes {
  defaultBranchRef { target { ... on Commit { history(first: 100, author: {id: "%s"}, since: "%s") {
    nodes { committedDate } } } } } } } } }"""


def fetch(query=QUERY):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}"},
    )
    out = json.load(urllib.request.urlopen(req))
    if "errors" in out:
        raise SystemExit(out["errors"])
    return out["data"]["viewer"]


def calendar(v):
    weeks = v["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]


def streaks(days):
    longest = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    counts = [n for _, n in days]
    if counts and counts[-1] == 0:  # today not started yet, streak still alive
        counts.pop()
    current = 0
    for n in reversed(counts):
        if not n:
            break
        current += 1
    return current, longest


def stats(v):
    c = v["contributionsCollection"]
    current, longest = streaks(calendar(v))
    tiles = [
        (c["contributionCalendar"]["totalContributions"], "contributions"),
        (c["totalCommitContributions"], "commits"),
        (c["totalPullRequestContributions"], "pull requests"),
        (v["repositories"]["totalCount"], "repositories"),
        (current, "day streak"),
        (longest, "longest streak"),
    ]
    W, H, left = 840, 130, 30
    tw = (W - 2 * left) / len(tiles)
    body = [f'<text x="{left}" y="30" class="title">Last 12 months</text>']
    for i, (n, label) in enumerate(tiles):
        x = left + i * tw + tw / 2
        body.append(f'<g class="rise" {delay(i, .12)}>'
                    f'<text x="{x:.1f}" y="88" text-anchor="middle" class="big">{n:,}</text>'
                    f'<text x="{x:.1f}" y="112" text-anchor="middle" class="lbl muted">{label}</text></g>')
    return svg(W, H, "".join(body), "Contribution stats for the last 12 months")


def activity(v):
    months = Counter()
    for date, n in calendar(v):
        months[date[:7]] += n
    keys = sorted(months)[-12:]
    W, H, top, base, left = 840, 240, 50, 200, 30
    peak = max(months[k] for k in keys) or 1
    bw = (W - 2 * left) / len(keys)
    body = [f'<text x="{left}" y="30" class="title">Contributions by month</text>',
            f'<line x1="{left}" x2="{W - left}" y1="{base}" y2="{base}" class="axis"/>']
    for i, k in enumerate(keys):
        h = (base - top - 16) * months[k] / peak
        x = left + i * bw
        month = dt.date(int(k[:4]), int(k[5:]), 1).strftime("%b")
        body.append(f'<rect x="{x + 8:.1f}" y="{base - h:.1f}" width="{bw - 16:.1f}" height="{h:.1f}" rx="2" class="bar grow-y" {delay(i)}/>')
        body.append(f'<text x="{x + bw / 2:.1f}" y="{base - h - 6:.1f}" text-anchor="middle" class="lbl fade" {delay(i)}>{months[k]}</text>')
        body.append(f'<text x="{x + bw / 2:.1f}" y="{base + 18}" text-anchor="middle" class="lbl muted">{month}</text>')
    return svg(W, H, "".join(body), "Monthly contributions over the last 12 months")


def weekdays(v):
    days = Counter()
    for date, n in calendar(v):
        days[dt.date.fromisoformat(date).weekday()] += n
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    W, H, top, base, left = 410, 260, 50, 220, 20
    peak = max(days.values()) or 1
    bw = (W - 2 * left) / 7
    body = [f'<text x="{left}" y="30" class="title">By weekday</text>',
            f'<line x1="{left}" x2="{W - left}" y1="{base}" y2="{base}" class="axis"/>']
    for i in range(7):
        h = (base - top - 16) * days[i] / peak
        x = left + i * bw
        body.append(f'<rect x="{x + 6:.1f}" y="{base - h:.1f}" width="{bw - 12:.1f}" height="{h:.1f}" rx="2" class="bar grow-y" {delay(i)}/>')
        body.append(f'<text x="{x + bw / 2:.1f}" y="{base - h - 6:.1f}" text-anchor="middle" class="lbl fade" {delay(i)}>{days[i]}</text>')
        body.append(f'<text x="{x + bw / 2:.1f}" y="{base + 18}" text-anchor="middle" class="lbl muted">{names[i]}</text>')
    return svg(W, H, "".join(body), "Contributions by day of the week")


def heatmap(v):
    weeks = v["contributionsCollection"]["contributionCalendar"]["weeks"]
    peak = max((d["contributionCount"] for w in weeks for d in w["contributionDays"]), default=0) or 1
    W, left, top, cell = 840, 30, 64, 15
    H = top + 7 * cell + 34
    body = [f'<text x="{left}" y="30" class="title">Every day of the year</text>']
    last = None
    for i, w in enumerate(weeks):
        x = left + i * cell
        firsts = [d["date"] for d in w["contributionDays"] if d["date"].endswith("-01")]
        m = firsts[0][5:7] if firsts else None
        if m and m != last and 2 < i < len(weeks) - 2:
            body.append(f'<text x="{x}" y="{top - 8}" class="lbl muted">{dt.date(2000, int(m), 1):%b}</text>')
            last = m
        for d in w["contributionDays"]:
            n = d["contributionCount"]
            row = dt.date.fromisoformat(d["date"]).isoweekday() % 7
            cls = f'cell l{min(4, 1 + int(4 * n / peak))}' if n else "empty"
            body.append(f'<rect x="{x}" y="{top + row * cell}" width="12" height="12" rx="2" class="{cls} pop" '
                        f'style="animation-delay:{(i + row) * .012:.3f}s"><title>{d["date"]}: {n}</title></rect>')
    y = H - 14
    body.append(f'<text x="{W - 210}" y="{y + 10}" class="lbl muted">less</text>')
    for k, cls in enumerate(["empty", "cell l1", "cell l2", "cell l3", "cell l4"]):
        body.append(f'<rect x="{W - 180 + k * 16}" y="{y}" width="12" height="12" rx="2" class="{cls}"/>')
    body.append(f'<text x="{W - 94}" y="{y + 10}" class="lbl muted">more</text>')
    return svg(W, H, "".join(body), "Contribution heatmap for the last 12 months")


def trend(v):
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"])
             for w in v["contributionsCollection"]["contributionCalendar"]["weeks"]]
    W, H, top, base, left = 840, 200, 50, 170, 30
    peak = max(weeks) or 1
    step = (W - 2 * left) / (len(weeks) - 1)
    pts = [(left + i * step, base - (base - top) * n / peak) for i, n in enumerate(weeks)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    best = max(range(len(weeks)), key=weeks.__getitem__)
    bx, by = pts[best]
    body = [f'<text x="{left}" y="30" class="title">Weekly trend</text>',
            f'<line x1="{left}" x2="{W - left}" y1="{base}" y2="{base}" class="axis"/>',
            f'<path d="{line} L{W - left},{base} L{left},{base} Z" class="area fade" style="animation-delay:1.2s"/>',
            f'<path d="{line}" pathLength="1" class="line draw"/>',
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="4" class="bar fade" style="animation-delay:1.6s"/>',
            f'<text x="{min(bx, W - left):.1f}" y="{by - 10:.1f}" text-anchor="{"end" if bx > W - 100 else "middle"}" class="lbl fade" style="animation-delay:1.6s">'
            f'best week: {weeks[best]}</text>']
    return svg(W, H, "".join(body), "Weekly contributions over the last 12 months")


# ponytail: fixed IST offset, swap for zoneinfo if the profile owner moves timezones
TZ = dt.timezone(dt.timedelta(hours=5, minutes=30))


@functools.cache
def commit_hours(user_id):
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    repos = fetch(COMMITS % (user_id, since))["repositories"]["nodes"]
    hours = Counter()
    for r in repos:
        for c in ((r["defaultBranchRef"] or {}).get("target") or {}).get("history", {}).get("nodes", []):
            hours[dt.datetime.fromisoformat(c["committedDate"].replace("Z", "+00:00")).astimezone(TZ).hour] += 1
    return hours


def clock(v):
    hours = commit_hours(v["id"])
    W, H, cx, cy, r0, r1 = 410, 260, 205, 140, 30, 92
    peak = max(hours.values(), default=0) or 1
    body = [f'<text x="20" y="30" class="title">Commit clock</text>',
            f'<circle cx="{cx}" cy="{cy}" r="{r1 + 6}" class="ring"/>']
    for h in range(24):
        a = math.radians(h * 15 - 90)
        r = r0 + (r1 - r0) * hours[h] / peak
        if hours[h]:
            body.append(f'<line x1="{cx + r0 * math.cos(a):.1f}" y1="{cy + r0 * math.sin(a):.1f}" '
                        f'x2="{cx + r * math.cos(a):.1f}" y2="{cy + r * math.sin(a):.1f}" pathLength="1" class="spoke" '
                        f'{delay(h, .04)}><title>{h:02d}:00, {hours[h]} commits</title></line>')
        if h % 6 == 0:
            lx, ly = cx + (r1 + 20) * math.cos(a), cy + (r1 + 20) * math.sin(a) + 4
            body.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" class="lbl muted">{h:02d}</text>')
    top = max(range(24), key=lambda h: hours[h])
    body.append(f'<text x="{cx}" y="{cy - 3}" text-anchor="middle" class="lbl muted">peak</text>'
                f'<text x="{cx}" y="{cy + 12}" text-anchor="middle" class="lbl">{top:02d}:00</text>')
    body.append(f'<text x="390" y="30" text-anchor="end" class="lbl muted">{sum(hours.values())} commits, IST</text>')
    return svg(W, H, "".join(body), f"Commits by hour of day, busiest at {top:02d}:00 IST")



# ponytail: notebooks are skipped because their bytes are mostly cell output, not code
SKIP_LANGS = {"Jupyter Notebook"}


def lang_share(v):
    total = Counter()
    for r in v["repositories"]["nodes"]:
        for e in r["languages"]["edges"]:
            if e["node"]["name"] not in SKIP_LANGS:
                total[e["node"]["name"]] += e["size"]
    return total


def languages(v):
    total = lang_share(v)
    top = total.most_common(6)
    s = sum(total.values()) or 1
    W, H, left, bar_x, row = 840, 230, 30, 160, 28
    body = [f'<text x="{left}" y="30" class="title">Languages</text>']
    for i, (name, size) in enumerate(top):
        y = 46 + i * row
        w = (W - bar_x - 70) * size / top[0][1]
        body.append(f'<text x="{left}" y="{y + 15}" class="val">{name}</text>')
        body.append(f'<rect x="{bar_x}" y="{y + 3}" width="{w:.1f}" height="15" rx="2" class="bar grow-x" {delay(i, .1)}/>')
        body.append(f'<text x="{bar_x + w + 8:.1f}" y="{y + 15}" class="lbl fade" {delay(i, .1)}>{100 * size / s:.1f}%</text>')
    return svg(W, H, "".join(body), "Language share across repositories")


def agent_block(v):
    c = v["contributionsCollection"]
    days = calendar(v)
    current, longest = streaks(days)
    week = Counter()
    for date, n in days:
        week[dt.date.fromisoformat(date).strftime("%A")] += n
    total = lang_share(v)
    s = sum(total.values()) or 1
    langs = ", ".join(f"{k} {100 * n / s:.0f}%" for k, n in total.most_common(4))
    hours = commit_hours(v["id"])
    return "\n".join([
        f"- Updated: {dt.date.today().isoformat()}, covering the last 12 months, public and private work",
        f"- Contributions: {c['contributionCalendar']['totalContributions']}; commits: {c['totalCommitContributions']}; "
        f"pull requests: {c['totalPullRequestContributions']}; repositories owned: {v['repositories']['totalCount']}",
        f"- Streak: current {current} days, longest {longest} days",
        f"- Busiest weekday: {week.most_common(1)[0][0]}; peak commit hour: {max(range(24), key=lambda h: hours[h]):02d}:00 IST",
        f"- Languages by code size: {langs}",
    ])


def splice(text, block, start="<!-- agent-stats:start -->", end="<!-- agent-stats:end -->"):
    i, j = text.index(start) + len(start), text.index(end)
    return text[:i] + "\n" + block + "\n" + text[j:]


if __name__ == "__main__":
    v = fetch()
    os.makedirs("assets", exist_ok=True)
    for fn in (stats, heatmap, trend, activity, weekdays, clock, languages):
        with open(f"assets/{fn.__name__}.svg", "w") as f:
            f.write(fn(v))
        print("wrote", fn.__name__)
    with open("README.md") as f:
        readme = f.read()
    with open("README.md", "w") as f:
        f.write(splice(readme, agent_block(v)))
    print("wrote README stats")
    c, l = streaks([("a", 1), ("b", 0), ("c", 2), ("d", 3), ("e", 0)])
    assert (c, l) == (2, 2), (c, l)
    assert splice("a<!-- agent-stats:start -->old<!-- agent-stats:end -->b", "new") == \
        "a<!-- agent-stats:start -->\nnew\n<!-- agent-stats:end -->b"
