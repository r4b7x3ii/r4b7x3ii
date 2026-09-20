#!/usr/bin/env python3
import base64
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path

USERNAME = "r4b7x3ii"
PROFILE_SVG = Path("profile.svg")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")


def request_json(url, *, method="GET", data=None, headers=None):
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-updater",
    }
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    if headers:
        h.update(headers)
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_repositories():
    repos = request_json(
        f"https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=updated&type=owner"
    )
    # Public repositories owned by the user. Keep GitHub's updated ordering.
    return [r for r in repos if r.get("owner", {}).get("login", "").lower() == USERNAME.lower()]


def get_contributions():
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                contributionLevel
              }
            }
          }
        }
      }
    }
    """
    payload = request_json(
        "https://api.github.com/graphql",
        method="POST",
        data={"query": query, "variables": {"login": USERNAME}},
    )
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def extract_avatar_data_uri():
    # Preserve the avatar already embedded in profile.svg so the workflow needs no extra binary file.
    if PROFILE_SVG.exists():
        text = PROFILE_SVG.read_text(encoding="utf-8")
        match = re.search(r'href="(data:image/(?:png|jpeg);base64,[^"]+)"', text)
        if match:
            return match.group(1)
    return ""


def repo_icon(x, y):
    return f'''<g transform="translate({x} {y})" class="fg">
      <path d="M2 2.5h9.5a2 2 0 0 1 2 2v11H4a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" stroke-width="1.7"/>
      <path d="M4.5 2.5v13" fill="none" stroke="currentColor" stroke-width="1.7"/>
      <circle cx="8.7" cy="8.2" r="1.35" fill="currentColor"/>
    </g>'''


def level_to_num(level):
    return {
        "NONE": 0,
        "FIRST_QUARTILE": 1,
        "SECOND_QUARTILE": 2,
        "THIRD_QUARTILE": 3,
        "FOURTH_QUARTILE": 4,
    }.get(level, 0)


def build_svg(repos, calendar, avatar_uri):
    weeks = calendar.get("weeks", [])
    total = calendar.get("totalContributions", 0)
    repo_count = len(repos)

    row_h = 68
    repo_box_h = 92 + max(1, repo_count) * row_h
    footer_gap = 24
    W = 1000
    hero_h = 430
    chart_y = 460
    chart_h = 395
    repos_y = chart_y + chart_h + 28
    H = repos_y + repo_box_h + footer_gap + 20

    out = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
  :root {{
    --bg:#ffffff; --panel:#f5f5f5; --panel2:#eeeeee; --fg:#111111; --muted:#5d5d5d;
    --line:#111111; --softline:#b7b7b7;
    --cell0:#ececec; --cell1:#c9c9c9; --cell2:#969696; --cell3:#5c5c5c; --cell4:#111111;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0d1117; --panel:#161b22; --panel2:#21262d; --fg:#f0f6fc; --muted:#8b949e;
      --line:#f0f6fc; --softline:#484f58;
      --cell0:#21262d; --cell1:#30363d; --cell2:#6e7681; --cell3:#b1bac4; --cell4:#f0f6fc;
    }}
  }}
  .bg{{fill:var(--bg)}} .panel{{fill:var(--panel)}} .panel2{{fill:var(--panel2)}}
  .fg{{fill:var(--fg);color:var(--fg)}} .muted{{fill:var(--muted)}} .line{{stroke:var(--line)}} .softline{{stroke:var(--softline)}}
  .title{{font:800 62px ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:var(--fg)}}
  .section{{font:800 36px ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:var(--fg)}}
  .mono{{font:20px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;fill:var(--fg)}}
  .mono-sm{{font:16px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;fill:var(--fg)}}
  .mono-xs{{font:14px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;fill:var(--muted)}}
  .repo{{font:700 21px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;fill:var(--fg)}}
  .pixel{{shape-rendering:crispEdges}}
</style>
<rect class="bg" width="{W}" height="{H}" rx="8"/>
<rect x="8" y="8" width="984" height="{H-16}" fill="none" class="line" stroke-width="3"/>

<!-- Hero -->
<text x="58" y="150" class="title">Hello.</text>
<text x="58" y="221" class="title">I’m {USERNAME}.</text>
<text x="61" y="268" class="mono">I code, error happens, i sleep</text>
<text x="61" y="298" class="mono">like nothing happened.</text>
<rect x="60" y="336" width="238" height="56" class="panel2 line" stroke-width="2"/>
<text x="90" y="372" class="mono">Known as Werus</text>

<!-- Avatar -->
<rect x="548" y="55" width="384" height="342" class="panel line" stroke-width="3"/>
<rect x="548" y="55" width="384" height="38" class="panel2 line" stroke-width="3"/>
<circle cx="896" cy="74" r="8" fill="none" class="line" stroke-width="2"/>
<circle cx="870" cy="74" r="8" fill="none" class="line" stroke-width="2"/>
<text x="566" y="80" class="mono-sm">{USERNAME}.exe</text>
<defs><clipPath id="avatarClip"><rect x="560" y="104" width="360" height="280" rx="2"/></clipPath></defs>
''']

    if avatar_uri:
        out.append(f'<image href="{avatar_uri}" x="560" y="104" width="360" height="280" preserveAspectRatio="xMidYMid slice" clip-path="url(#avatarClip)"/>')
    else:
        out.append('<rect x="560" y="104" width="360" height="280" class="panel2"/>')
    out.append('<rect x="560" y="104" width="360" height="280" fill="none" class="line" stroke-width="2"/>')

    # Contribution chart
    out.append(f'''
<rect x="28" y="{chart_y}" width="944" height="{chart_h}" class="panel line" stroke-width="2.5"/>
<text x="58" y="{chart_y+58}" class="section">Contribution Chart</text>
<text x="720" y="{chart_y+53}" class="mono-xs">{total} contributions in the last year</text>
<rect x="52" y="{chart_y+92}" width="896" height="250" class="bg line" stroke-width="2.5"/>
<rect x="52" y="{chart_y+92}" width="896" height="42" class="panel2 line" stroke-width="2.5"/>
<circle cx="77" cy="{chart_y+113}" r="7" fill="none" class="line" stroke-width="2"/>
<circle cx="100" cy="{chart_y+113}" r="7" fill="none" class="line" stroke-width="2"/>
<text x="129" y="{chart_y+119}" class="mono-sm">contributions.exe</text>
''')

    # Dynamic month labels based on week start dates.
    last_month = None
    for ci, week in enumerate(weeks):
        days = week.get("contributionDays", [])
        if not days:
            continue
        dt = datetime.fromisoformat(days[0]["date"])
        month = dt.strftime("%b")
        if month != last_month:
            x = 122 + ci * 15
            if x < 915:
                out.append(f'<text x="{x}" y="{chart_y+164}" class="mono-xs">{month}</text>')
            last_month = month

    for label, yy in [("Mon", chart_y+197), ("Wed", chart_y+227), ("Fri", chart_y+257)]:
        out.append(f'<text x="70" y="{yy}" class="mono-xs">{label}</text>')

    start_x, start_y, cell, gap = 122, chart_y + 178, 11, 4
    for c, week in enumerate(weeks[-53:]):
        for r, day in enumerate(week.get("contributionDays", [])):
            lvl = level_to_num(day.get("contributionLevel"))
            out.append(
                f'<rect x="{start_x+c*(cell+gap)}" y="{start_y+r*(cell+gap)}" width="{cell}" height="{cell}" fill="var(--cell{lvl})" class="pixel"/>'
            )

    out.append(f'''
<text x="70" y="{chart_y+323}" class="mono-xs">Less</text>
<rect x="122" y="{chart_y+311}" width="14" height="14" fill="var(--cell0)"/>
<rect x="144" y="{chart_y+311}" width="14" height="14" fill="var(--cell1)"/>
<rect x="166" y="{chart_y+311}" width="14" height="14" fill="var(--cell2)"/>
<rect x="188" y="{chart_y+311}" width="14" height="14" fill="var(--cell3)"/>
<rect x="210" y="{chart_y+311}" width="14" height="14" fill="var(--cell4)"/>
<text x="234" y="{chart_y+323}" class="mono-xs">More</text>
''')

    # Repository list
    out.append(f'''
<rect x="28" y="{repos_y}" width="944" height="{repo_box_h}" class="panel line" stroke-width="2.5"/>
<text x="58" y="{repos_y+58}" class="section">Repository List</text>
<text x="808" y="{repos_y+53}" class="mono-xs">{repo_count} public repos</text>
''')

    y0 = repos_y + 86
    if not repos:
        out.append(f'<text x="70" y="{y0+38}" class="mono">No public repositories found.</text>')
    for i, repo in enumerate(repos):
        y = y0 + i * row_h
        name = escape(repo.get("name", ""))
        lang = escape(repo.get("language") or "—")
        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        out.append(f'<rect x="58" y="{y}" width="884" height="56" class="bg softline" stroke-width="1.5"/>')
        out.append(repo_icon(78, y + 18))
        out.append(f'<text x="112" y="{y+35}" class="repo">{name}</text>')
        out.append(f'<text x="650" y="{y+34}" class="mono-xs">{lang}</text>')
        out.append(f'<text x="770" y="{y+34}" class="mono-xs">★ {stars}   ⑂ {forks}</text>')
        out.append(f'<rect x="885" y="{y+9}" width="42" height="38" class="panel2 line" stroke-width="1.5"/>')
        out.append(repo_icon(896, y + 19))

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out.append(f'<text x="60" y="{H-34}" class="mono-xs">updated automatically · {updated}</text>')
    out.append('</svg>')
    return "".join(out)


def main():
    avatar_uri = extract_avatar_data_uri()
    repos = get_repositories()
    calendar = get_contributions()
    PROFILE_SVG.write_text(build_svg(repos, calendar, avatar_uri), encoding="utf-8")
    print(f"Updated {PROFILE_SVG} with {len(repos)} repos and {calendar.get('totalContributions', 0)} contributions.")


if __name__ == "__main__":
    main()
