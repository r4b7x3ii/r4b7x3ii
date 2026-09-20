#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import urllib.request
from datetime import date, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path

USERNAME = "r4b7x3ii"
REPOSITORY = "r4b7x3ii/r4b7x3ii"

PROFILE_SVG = Path("profile.svg")
README = Path("README.md")

TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")


def request_bytes(url, *, method="GET", data=None, headers=None):
    h = {
        "User-Agent": f"{USERNAME}-profile-updater",
        "Accept": "*/*",
    }
    if TOKEN and "api.github.com" in url:
        h["Authorization"] = f"Bearer {TOKEN}"
    if headers:
        h.update(headers)

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def request_json(url, *, method="GET", data=None):
    return json.loads(
        request_bytes(
            url,
            method=method,
            data=data,
            headers={"Accept": "application/vnd.github+json"},
        ).decode("utf-8")
    )


def request_text(url):
    return request_bytes(url).decode("utf-8", errors="replace")


def get_repositories():
    repos = request_json(
        f"https://api.github.com/users/{USERNAME}/repos"
        "?per_page=100&sort=updated&type=owner"
    )
    return [
        repo
        for repo in repos
        if repo.get("owner", {}).get("login", "").lower() == USERNAME.lower()
        and not repo.get("private", False)
    ]


class ContributionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        day = attrs.get("data-date")
        level = attrs.get("data-level")
        if not day or level is None:
            return
        try:
            level_num = max(0, min(4, int(level)))
        except (TypeError, ValueError):
            return
        self.days[day] = level_num


def contributions_from_profile():
    # Read the same public contribution calendar GitHub displays on the profile.
    html = request_text(f"https://github.com/users/{USERNAME}/contributions")
    parser = ContributionParser()
    parser.feed(html)
    return parser.days


def contributions_from_graphql():
    # Fallback in case GitHub changes the profile-calendar HTML.
    if not TOKEN:
        return {}

    query = '''
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionLevel
              }
            }
          }
        }
      }
    }
    '''

    payload = request_json(
        "https://api.github.com/graphql",
        method="POST",
        data={"query": query, "variables": {"login": USERNAME}},
    )

    levels = {
        "NONE": 0,
        "FIRST_QUARTILE": 1,
        "SECOND_QUARTILE": 2,
        "THIRD_QUARTILE": 3,
        "FOURTH_QUARTILE": 4,
    }

    days = {}
    try:
        weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    except (KeyError, TypeError):
        return days

    for week in weeks:
        for day in week.get("contributionDays", []):
            days[day["date"]] = levels.get(day.get("contributionLevel"), 0)
    return days


def get_contributions():
    try:
        days = contributions_from_profile()
        if days:
            return days
    except Exception as exc:
        print(f"Public contribution fetch failed: {exc}")

    try:
        return contributions_from_graphql()
    except Exception as exc:
        print(f"GraphQL contribution fallback failed: {exc}")
        return {}


def get_avatar_data_uri():
    # Always use the user's current GitHub avatar.
    user = request_json(f"https://api.github.com/users/{USERNAME}")
    avatar_url = user.get("avatar_url")
    if not avatar_url:
        return ""

    req = urllib.request.Request(
        avatar_url,
        headers={"User-Agent": f"{USERNAME}-profile-updater"},
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
        mime = response.headers.get_content_type() or "image/png"

    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def repo_icon(x, y):
    return f'''<g transform="translate({x} {y})" class="fg">
      <path d="M2 2.5h9.5a2 2 0 0 1 2 2v11H4a2 2 0 0 1-2-2z"
            fill="none" stroke="currentColor" stroke-width="1.7"/>
      <path d="M4.5 2.5v13" fill="none"
            stroke="currentColor" stroke-width="1.7"/>
      <circle cx="8.7" cy="8.2" r="1.35" fill="currentColor"/>
    </g>'''


def title_text(x, y, text):
    return f'''<text x="{x}" y="{y}" class="title">{escape(text)}
      <animate attributeName="fill"
        values="#ff5f56;#bf5af2;#0a84ff;#30d158;#ff9f0a;#ff5f56"
        dur="9s" repeatCount="indefinite"/>
    </text>'''


def pixel_game(y):
    return f'''
<!-- Auto-playing pixel game -->
<rect x="28" y="{y}" width="944" height="286" class="panel line" stroke-width="2.5"/>
<text x="58" y="{y+58}" class="section">Auto Game</text>

<rect x="52" y="{y+88}" width="896" height="162" class="bg line" stroke-width="2.5"/>
<rect x="52" y="{y+88}" width="896" height="38" class="panel2 line" stroke-width="2.5"/>
<circle cx="77" cy="{y+107}" r="7" fill="none" class="line" stroke-width="2"/>
<circle cx="100" cy="{y+107}" r="7" fill="none" class="line" stroke-width="2"/>
<text x="129" y="{y+113}" class="mono-sm">bug-runner.exe</text>
<text x="814" y="{y+113}" class="mono-xs">AUTO
  <animate attributeName="opacity" values=".35;1;.35" dur="1s" repeatCount="indefinite"/>
</text>

<g fill="var(--muted)">
  <rect x="190" y="{y+147}" width="4" height="4">
    <animate attributeName="opacity" values=".15;.8;.15" dur="1.8s" repeatCount="indefinite"/>
  </rect>
  <rect x="434" y="{y+157}" width="4" height="4">
    <animate attributeName="opacity" values=".8;.15;.8" dur="2.4s" repeatCount="indefinite"/>
  </rect>
  <rect x="704" y="{y+143}" width="4" height="4">
    <animate attributeName="opacity" values=".2;1;.2" dur="1.3s" repeatCount="indefinite"/>
  </rect>
</g>

<line x1="78" y1="{y+220}" x2="922" y2="{y+220}" class="line" stroke-width="3"/>
<g stroke="var(--softline)" stroke-width="2">
  <line x1="110" y1="{y+228}" x2="150" y2="{y+228}"/>
  <line x1="315" y1="{y+228}" x2="370" y2="{y+228}"/>
  <line x1="612" y1="{y+228}" x2="680" y2="{y+228}"/>
  <line x1="810" y1="{y+228}" x2="865" y2="{y+228}"/>
</g>

<!-- player -->
<g transform="translate(0 0)" class="fg">
  <animateTransform attributeName="transform" type="translate"
    values="0 0;0 0;0 -42;0 -42;0 0;0 0"
    keyTimes="0;.29;.38;.49;.58;1"
    dur="3.8s" repeatCount="indefinite"/>
  <rect x="154" y="{y+186}" width="16" height="16" fill="currentColor"/>
  <rect x="150" y="{y+202}" width="24" height="10" fill="currentColor"/>
  <rect x="150" y="{y+212}" width="7" height="8" fill="currentColor"/>
  <rect x="167" y="{y+212}" width="7" height="8" fill="currentColor"/>
  <rect x="165" y="{y+190}" width="3" height="3" fill="var(--bg)"/>
</g>

<!-- moving bug -->
<g class="fg">
  <animateTransform attributeName="transform" type="translate"
    from="720 0" to="-30 0" dur="3.8s" repeatCount="indefinite"/>
  <rect x="100" y="{y+202}" width="20" height="14" fill="currentColor"/>
  <rect x="96" y="{y+207}" width="4" height="4" fill="currentColor"/>
  <rect x="120" y="{y+207}" width="4" height="4" fill="currentColor"/>
  <rect x="102" y="{y+198}" width="4" height="4" fill="currentColor"/>
  <rect x="114" y="{y+198}" width="4" height="4" fill="currentColor"/>
</g>

<!-- floating pickup -->
<g class="fg">
  <animateTransform attributeName="transform" type="translate"
    values="0 0;0 -8;0 0" dur="1.2s" repeatCount="indefinite"/>
  <rect x="500" y="{y+163}" width="12" height="12" fill="none"
        stroke="currentColor" stroke-width="3"/>
  <rect x="504" y="{y+167}" width="4" height="4" fill="currentColor"/>
</g>
'''


def build_svg(repos, contributions, avatar_uri):
    repo_count = len(repos)

    W = 1000
    chart_y = 460
    chart_h = 360
    game_y = chart_y + chart_h + 28
    game_h = 286
    repos_y = game_y + game_h + 28

    row_h = 68
    repo_box_h = 92 + max(1, repo_count) * row_h
    H = repos_y + repo_box_h + 28

    out = [f'''<svg xmlns="http://www.w3.org/2000/svg"
  width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
  :root {{
    --bg:#ffffff; --panel:#f5f5f5; --panel2:#eeeeee;
    --fg:#111111; --muted:#5d5d5d; --line:#111111; --softline:#b7b7b7;
    --cell0:#ececec; --cell1:#c9c9c9; --cell2:#969696;
    --cell3:#5c5c5c; --cell4:#111111;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0d1117; --panel:#161b22; --panel2:#21262d;
      --fg:#f0f6fc; --muted:#8b949e; --line:#f0f6fc; --softline:#484f58;
      --cell0:#21262d; --cell1:#30363d; --cell2:#6e7681;
      --cell3:#b1bac4; --cell4:#f0f6fc;
    }}
  }}

  .bg{{fill:var(--bg)}}
  .panel{{fill:var(--panel)}}
  .panel2{{fill:var(--panel2)}}
  .fg{{fill:var(--fg);color:var(--fg)}}
  .muted{{fill:var(--muted)}}
  .line{{stroke:var(--line)}}
  .softline{{stroke:var(--softline)}}
  .title{{
    font:800 62px ui-sans-serif,system-ui,-apple-system,
         BlinkMacSystemFont,"Segoe UI",sans-serif;
  }}
  .section{{
    font:800 36px ui-sans-serif,system-ui,-apple-system,
         BlinkMacSystemFont,"Segoe UI",sans-serif;
    fill:var(--fg);
  }}
  .mono{{
    font:20px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
    fill:var(--fg);
  }}
  .mono-sm{{
    font:16px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
    fill:var(--fg);
  }}
  .mono-xs{{
    font:14px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
    fill:var(--muted);
  }}
  .repo{{
    font:700 21px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
    fill:var(--fg);
  }}
  .pixel{{shape-rendering:crispEdges}}
</style>

<rect class="bg" width="{W}" height="{H}" rx="8"/>
<rect x="8" y="8" width="984" height="{H-16}"
      fill="none" class="line" stroke-width="3"/>

<!-- Hero -->
''']

    out.append(title_text(58, 150, "Hello."))
    out.append(title_text(58, 221, f"I’m {USERNAME}."))

    out.append(f'''
<text x="61" y="268" class="mono">I code, error happens, i sleep</text>
<text x="61" y="298" class="mono">like nothing happened.</text>

<rect x="60" y="336" width="238" height="56"
      class="panel2 line" stroke-width="2"/>
<text x="90" y="372" class="mono">Known as Werus</text>

<!-- Avatar -->
<rect x="548" y="55" width="384" height="342"
      class="panel line" stroke-width="3"/>
<rect x="548" y="55" width="384" height="38"
      class="panel2 line" stroke-width="3"/>
<circle cx="896" cy="74" r="8" fill="none" class="line" stroke-width="2"/>
<circle cx="870" cy="74" r="8" fill="none" class="line" stroke-width="2"/>
<text x="566" y="80" class="mono-sm">{USERNAME}.exe</text>

<defs>
  <clipPath id="avatarClip">
    <rect x="560" y="104" width="360" height="280" rx="2"/>
  </clipPath>
</defs>
''')

    if avatar_uri:
        out.append(
            f'<image href="{avatar_uri}" x="560" y="104" width="360" height="280" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#avatarClip)"/>'
        )
    else:
        out.append('<rect x="560" y="104" width="360" height="280" class="panel2"/>')

    out.append(
        '<rect x="560" y="104" width="360" height="280" '
        'fill="none" class="line" stroke-width="2"/>'
    )

    out.append(f'''
<!-- Contribution chart -->
<rect x="28" y="{chart_y}" width="944" height="{chart_h}"
      class="panel line" stroke-width="2.5"/>
<text x="58" y="{chart_y+58}" class="section">Contribution Chart</text>

<rect x="52" y="{chart_y+92}" width="896" height="224"
      class="bg line" stroke-width="2.5"/>
<rect x="52" y="{chart_y+92}" width="896" height="42"
      class="panel2 line" stroke-width="2.5"/>
<circle cx="77" cy="{chart_y+113}" r="7"
        fill="none" class="line" stroke-width="2"/>
<circle cx="100" cy="{chart_y+113}" r="7"
        fill="none" class="line" stroke-width="2"/>
<text x="129" y="{chart_y+119}" class="mono-sm">contributions.exe</text>
''')

    today = date.today()
    days_since_sunday = (today.weekday() + 1) % 7
    current_sunday = today - timedelta(days=days_since_sunday)
    first_sunday = current_sunday - timedelta(weeks=52)

    last_month = None
    for c in range(53):
        week_start = first_sunday + timedelta(weeks=c)
        month = week_start.strftime("%b")
        if month != last_month:
            x = 122 + c * 15
            if x < 915:
                out.append(
                    f'<text x="{x}" y="{chart_y+164}" class="mono-xs">{month}</text>'
                )
            last_month = month

    for label, yy in [
        ("Mon", chart_y + 197),
        ("Wed", chart_y + 227),
        ("Fri", chart_y + 257),
    ]:
        out.append(f'<text x="70" y="{yy}" class="mono-xs">{label}</text>')

    start_x = 122
    start_y = chart_y + 178
    cell = 11
    gap = 4

    for c in range(53):
        week_start = first_sunday + timedelta(weeks=c)
        for r in range(7):
            day = week_start + timedelta(days=r)
            level = contributions.get(day.isoformat(), 0)
            out.append(
                f'<rect x="{start_x + c*(cell+gap)}" '
                f'y="{start_y + r*(cell+gap)}" '
                f'width="{cell}" height="{cell}" '
                f'fill="var(--cell{level})" class="pixel"/>'
            )

    out.append(f'''
<text x="70" y="{chart_y+298}" class="mono-xs">Less</text>
<rect x="122" y="{chart_y+286}" width="14" height="14" fill="var(--cell0)"/>
<rect x="144" y="{chart_y+286}" width="14" height="14" fill="var(--cell1)"/>
<rect x="166" y="{chart_y+286}" width="14" height="14" fill="var(--cell2)"/>
<rect x="188" y="{chart_y+286}" width="14" height="14" fill="var(--cell3)"/>
<rect x="210" y="{chart_y+286}" width="14" height="14" fill="var(--cell4)"/>
<text x="234" y="{chart_y+298}" class="mono-xs">More</text>
''')

    out.append(pixel_game(game_y))

    out.append(f'''
<!-- Repository list -->
<rect x="28" y="{repos_y}" width="944" height="{repo_box_h}"
      class="panel line" stroke-width="2.5"/>
<text x="58" y="{repos_y+58}" class="section">Repository List</text>
''')

    y0 = repos_y + 86
    if not repos:
        out.append(
            f'<text x="70" y="{y0+38}" class="mono">No public repositories found.</text>'
        )

    for i, repo in enumerate(repos):
        y = y0 + i * row_h
        name = escape(repo.get("name", ""))
        lang = escape(repo.get("language") or "—")
        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)

        out.append(
            f'<rect x="58" y="{y}" width="884" height="56" '
            f'class="bg softline" stroke-width="1.5"/>'
        )
        out.append(repo_icon(78, y + 18))
        out.append(f'<text x="112" y="{y+35}" class="repo">{name}</text>')
        out.append(f'<text x="650" y="{y+34}" class="mono-xs">{lang}</text>')
        out.append(
            f'<text x="770" y="{y+34}" class="mono-xs">'
            f'★ {stars}   ⑂ {forks}</text>'
        )
        out.append(
            f'<rect x="885" y="{y+9}" width="42" height="38" '
            f'class="panel2 line" stroke-width="1.5"/>'
        )
        out.append(repo_icon(896, y + 19))

    out.append("</svg>")
    return "".join(out)


def write_readme(svg_text):
    # Cache busting: README changes only when profile.svg content changes.
    version = hashlib.sha256(svg_text.encode("utf-8")).hexdigest()[:12]
    README.write_text(
        f'''<div align="center">

<img src="https://raw.githubusercontent.com/{REPOSITORY}/main/profile.svg?v={version}"
     alt="{USERNAME} — Known as Werus"
     width="100%" />

</div>
''',
        encoding="utf-8",
    )


def main():
    repos = get_repositories()
    contributions = get_contributions()
    avatar_uri = get_avatar_data_uri()

    svg_text = build_svg(repos, contributions, avatar_uri)
    PROFILE_SVG.write_text(svg_text, encoding="utf-8")
    write_readme(svg_text)

    print(
        f"Generated {PROFILE_SVG} and refreshed {README} "
        f"using {len(repos)} public repositories."
    )


if __name__ == "__main__":
    main()
