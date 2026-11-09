"""Render GitHub stats cards (stats.svg, languages.svg) into assets/ from the GraphQL API."""
import datetime as dt
import json
import os
import urllib.request

USER = os.environ.get("GH_USER", "NeoDrew")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = os.path.join(os.path.dirname(__file__), "..", "assets")

BG, BORDER, TITLE, TEXT, MUTED = "#0d1117", "#30363d", "#e6edf3", "#c9d1d9", "#8b949e"
FONT = "font-family:'Segoe UI',Ubuntu,Helvetica,Arial,sans-serif"
SKIP_LANGS = {"HTML", "CSS", "Jupyter Notebook", "Makefile", "Dockerfile", "Shell", "Batchfile", "PowerShell", "TeX"}


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    body = json.load(urllib.request.urlopen(req))
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch():
    base = gql(
        """query($u:String!){user(login:$u){createdAt
          pullRequests{totalCount}
          repositories(ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC,first:100){totalCount
            nodes{languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}}}""",
        u=USER,
    )["user"]
    year_q = """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){contributionsCollection(from:$f,to:$t){
          contributionCalendar{totalContributions}}}}"""
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(base["createdAt"].replace("Z", "+00:00"))
    all_time = 0
    cursor = start
    while cursor < now:
        end = min(cursor + dt.timedelta(days=365), now)
        cc = gql(year_q, u=USER, f=cursor.isoformat(), t=end.isoformat())["user"]["contributionsCollection"]
        all_time += cc["contributionCalendar"]["totalContributions"]
        cursor = end
    last_year = gql(
        """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){contributionsCollection(from:$f,to:$t){
          contributionCalendar{totalContributions weeks{contributionDays{contributionCount}}}}}}""",
        u=USER, f=(now - dt.timedelta(days=365)).isoformat(), t=now.isoformat(),
    )
    days = [d["contributionCount"] for w in last_year["user"]["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    langs = {}
    for repo in base["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            if name in SKIP_LANGS:
                continue
            size, color = langs.get(name, (0, e["node"]["color"] or MUTED))
            langs[name] = (size + e["size"], color)
    return {
        "last_year": last_year["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "all_time": all_time,
        "active_days": sum(1 for c in days if c),
        "best_day": max(days, default=0),
        "repos": base["repositories"]["totalCount"],
        "langs": sorted(langs.items(), key=lambda kv: -kv[1][0])[:6],
    }


def card(title, inner, height):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="{height}" viewBox="0 0 400 {height}">
<rect x="0.5" y="0.5" width="399" height="{height - 1}" rx="8" fill="{BG}" stroke="{BORDER}"/>
<text x="24" y="36" style="{FONT};font-size:16px;font-weight:600" fill="{TITLE}">{title}</text>
{inner}
</svg>
"""


def stats_svg(d):
    rows = [
        ("Contributions (last 12 months)", d["last_year"]),
        ("Active days (last 12 months)", d["active_days"]),
        ("Most contributions in a day", d["best_day"]),
        ("Public repos", d["repos"]),
    ]
    inner = "".join(
        f'<text x="24" y="{72 + i * 26}" style="{FONT};font-size:14px" fill="{MUTED}">{label}</text>'
        f'<text x="376" y="{72 + i * 26}" text-anchor="end" style="{FONT};font-size:14px;font-weight:600" fill="{TEXT}">{value:,}</text>'
        for i, (label, value) in enumerate(rows)
    )
    return card("GitHub stats", inner, 172)


def langs_svg(d):
    total = sum(size for _, (size, _) in d["langs"]) or 1
    bar, x = [], 24.0
    for _, (size, color) in d["langs"]:
        w = 352 * size / total
        bar.append(f'<rect x="{x:.2f}" y="54" width="{w:.2f}" height="8" fill="{color}"/>')
        x += w
    bar_svg = f'<clipPath id="c"><rect x="24" y="54" width="352" height="8" rx="4"/></clipPath><g clip-path="url(#c)">{"".join(bar)}</g>'
    items = []
    for i, (name, (size, color)) in enumerate(d["langs"]):
        cx, cy = 24 + (i % 2) * 180, 92 + (i // 2) * 26
        items.append(
            f'<circle cx="{cx + 5}" cy="{cy - 5}" r="5" fill="{color}"/>'
            f'<text x="{cx + 16}" y="{cy}" style="{FONT};font-size:14px" fill="{TEXT}">{name}</text>'
            f'<text x="{cx + 160}" y="{cy}" text-anchor="end" style="{FONT};font-size:13px" fill="{MUTED}">{100 * size / total:.1f}%</text>'
        )
    return card("Top languages", bar_svg + "".join(items), 172)


if __name__ == "__main__":
    data = fetch()
    with open(os.path.join(OUT, "stats.svg"), "w") as f:
        f.write(stats_svg(data))
    with open(os.path.join(OUT, "languages.svg"), "w") as f:
        f.write(langs_svg(data))
    print({k: v for k, v in data.items() if k != "langs"}, [n for n, _ in data["langs"]])
