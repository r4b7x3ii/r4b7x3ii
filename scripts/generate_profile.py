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

# Optional personal token secret for private-repo stats across the whole account.
# If absent, the script falls back to public-only data where necessary.
PROFILE_DATA_TOKEN = os.getenv("PROFILE_DATA_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")


def request_bytes(url, *, method="GET", data=None, headers=None, token=None):
    h = {
        "User-Agent": f"{USERNAME}-profile-updater",
        "Accept": "*/*",
    }
    active_token = token or PROFILE_DATA_TOKEN
    if active_token and ("api.github.com" in url or "raw.githubusercontent.com" in url):
        h["Authorization"] = f"Bearer {active_token}"
    if headers:
        h.update(headers)

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read(), response.headers


def request_json(url, *, method="GET", data=None, token=None):
    payload, _ = request_bytes(
        url,
        method=method,
        data=data,
        headers={"Accept": "application/vnd.github+json"},
        token=token,
    )
    return json.loads(payload.decode("utf-8"))


def request_text(url):
    payload, _ = request_bytes(url)
    return payload.decode("utf-8", errors="replace")


def get_repositories():
    # Prefer authenticated owner listing. With a PAT secret this can include private repos.
    repos = []
    tried_private = False
    if PROFILE_DATA_TOKEN:
        tried_private = True
        try:
            repos = request_json(
                "https://api.github.com/user/repos"
                "?per_page=100&sort=updated&visibility=all&affiliation=owner"
            )
        except Exception as exc:
            print(f"Authenticated repository fetch failed, falling back to public repos: {exc}")
            repos = []

    if not repos:
        repos = request_json(
            f"https://api.github.com/users/{USERNAME}/repos"
            "?per_page=100&sort=updated&type=owner"
        )

    repos = [
        repo for repo in repos
        if repo.get("owner", {}).get("login", "").lower() == USERNAME.lower()
    ]
    return repos, tried_private


def get_languages_breakdown(repos):
    totals = {}
    for repo in repos:
        languages_url = repo.get("languages_url")
        added = False
        if languages_url:
            try:
                lang_map = request_json(languages_url)
                if isinstance(lang_map, dict) and lang_map:
                    for lang, value in lang_map.items():
                        totals[lang] = totals.get(lang, 0) + int(value)
                    added = True
            except Exception:
                added = False
        if not added:
            lang = repo.get("language") or "Other"
            totals[lang] = totals.get(lang, 0) + 1
    return dict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True))


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
    html = request_text(f"https://github.com/users/{USERNAME}/contributions")
    parser = ContributionParser()
    parser.feed(html)
    return parser.days


def contributions_from_graphql():
    if not PROFILE_DATA_TOKEN:
        return {}

    query = """
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
    """
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
    user = request_json(f"https://api.github.com/users/{USERNAME}")
    avatar_url = user.get("avatar_url")
    if not avatar_url:
        return ""

    req = urllib.request.Request(
        avatar_url,
        headers={"User-Agent": f"{USERNAME}-profile-updater"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        data = response.read()
        mime = response.headers.get_content_type() or "image/png"

    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def repo_icon(x, y):
    return f'''<g transform="translate({x} {y})" class="fg">
      <path d="M2 2.5h9.5a2 2 0 0 1 2 2v11H4a2 2 0 0 1-2-2z"
            fill="none" stroke="currentColor" stroke-width="1.7"/>
      <path d="M4.5 2.5v13" fill="none" stroke="currentColor" stroke-width="1.7"/>
      <circle cx="8.7" cy="8.2" r="1.35" fill="currentColor"/>
    </g>'''


def title_text(x, y, text):
    return f'''<text x="{x}" y="{y}" class="title">{escape(text)}
      <animate attributeName="fill"
        values="#ff5f56;#ff9f0a;#ffd60a;#30d158;#64d2ff;#0a84ff;#bf5af2;#ff375f;#ff5f56"
        dur="10s" repeatCount="indefinite"/>
    </text>'''


def stack_card(x, y, w, h, label, value, color, delay):
    safe_label = escape(label)
    safe_value = escape(value)
    bar_max = max(30, w - 128)
    return f'''
<g>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" class="bg line" stroke-width="1.3"/>
  <circle cx="{x+22}" cy="{y+20}" r="7" fill="{color}">
    <animate attributeName="r" values="7;8.8;7" dur="1.8s" begin="{delay}s" repeatCount="indefinite"/>
  </circle>
  <text x="{x+38}" y="{y+25}" class="mono-sm">{safe_label}</text>
  <rect x="{x+18}" y="{y+34}" width="{bar_max}" height="9" rx="4.5" fill="var(--panel2)"/>
  <rect x="{x+18}" y="{y+34}" width="0" height="9" rx="4.5" fill="{color}">
    <animate attributeName="width" from="0" to="{bar_max}" dur="1.2s" begin="{delay}s" fill="freeze"/>
  </rect>
  <text x="{x+w-12}" y="{y+26}" text-anchor="end" class="mono-xs">{safe_value}</text>
</g>'''


def build_stack_panel(stack_items, repo_count, private_capable, y):
    colors = ["#ff5f56", "#ff9f0a", "#ffd60a", "#30d158", "#64d2ff", "#bf5af2"]
    panel = [
        f'''
<rect x="28" y="{y}" width="944" height="252" class="panel line" stroke-width="2.5"/>
<text x="58" y="{y+58}" class="section">Profile Stack</text>
<text x="760" y="{y+52}" class="mono-xs">{repo_count} repos scanned</text>
<text x="760" y="{y+72}" class="mono-xs">{'public + private' if private_capable else 'public only'}</text>
'''
    ]
    cols = 2
    card_w = 430
    card_h = 56
    start_x = 58
    start_y = y + 92
    gap_x = 26
    gap_y = 16

    for i, item in enumerate(stack_items[:6]):
        row = i // cols
        col = i % cols
        cx = start_x + col * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)
        label = item["label"]
        value = item["value"]
        color = colors[i % len(colors)]
        panel.append(stack_card(cx, cy, card_w, card_h, label, value, color, i * 0.16))
    return "".join(panel)



def build_game_panel(y):
    # Chrome-dino-inspired endless auto-play game rendered with pure SVG animations.
    # Three phases loop forever, each phase runs faster than the previous one.
    return f"""
<rect x="28" y="{y}" width="944" height="294" class="panel line" stroke-width="2.5"/>

<!-- game viewport -->
<rect x="52" y="{y+38}" width="896" height="222" class="bg line" stroke-width="2.5"/>
<rect x="52" y="{y+38}" width="896" height="42" class="panel2 line" stroke-width="2.5"/>
<circle cx="77" cy="{y+59}" r="7" fill="none" class="line" stroke-width="2"/>
<circle cx="100" cy="{y+59}" r="7" fill="none" class="line" stroke-width="2"/>
<text x="129" y="{y+65}" class="mono-sm">offline-dino.exe</text>

<!-- score -->
<text x="852" y="{y+65}" class="mono-xs" text-anchor="end">HI 0042</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">0000</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="1;0;0;0;0;0;0;0;0;0" keyTimes="0;.10;.11;1" dur="18s" repeatCount="indefinite"/>
  0008
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;1;0;0;0;0;0;0;0;0" keyTimes="0;.10;.20;.21;1" dur="18s" repeatCount="indefinite"/>
  0016
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;0;1;0;0;0;0;0;0;0" keyTimes="0;.20;.30;.31;1" dur="18s" repeatCount="indefinite"/>
  0024
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;0;0;1;0;0;0;0;0;0" keyTimes="0;.30;.40;.41;1" dur="18s" repeatCount="indefinite"/>
  0032
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;0;0;0;1;0;0;0;0;0" keyTimes="0;.40;.50;.51;1" dur="18s" repeatCount="indefinite"/>
  0040
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;0;0;0;0;1;0;0;0;0" keyTimes="0;.50;.60;.61;1" dur="18s" repeatCount="indefinite"/>
  0048
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;0;0;0;0;0;1;0;0;0" keyTimes="0;.60;.70;.71;1" dur="18s" repeatCount="indefinite"/>
  0058
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;0;0;0;0;0;0;1;0;0" keyTimes="0;.70;.80;.81;1" dur="18s" repeatCount="indefinite"/>
  0068
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;0;0;0;0;0;0;0;1;0" keyTimes="0;.80;.90;.91;1" dur="18s" repeatCount="indefinite"/>
  0078
</text>
<text x="917" y="{y+65}" class="mono-xs" text-anchor="end">
  <animate attributeName="opacity" values="0;0;0;0;0;0;0;0;0;1" keyTimes="0;.90;.99;1;1" dur="18s" repeatCount="indefinite"/>
  0090
</text>

<!-- environment -->
<circle cx="800" cy="{y+112}" r="22" fill="none" class="softline" stroke-width="2"/>
<g class="muted">
  <path d="M170 {y+120} q10 -10 20 0 q4 -12 18 -8 q14 4 13 16 h-55 q-5 -10 4 -18z" fill="currentColor" opacity="0.55">
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-46 0" dur="11s" repeatCount="indefinite"/>
  </path>
  <path d="M470 {y+103} q10 -10 20 0 q4 -12 18 -8 q14 4 13 16 h-55 q-5 -10 4 -18z" fill="currentColor" opacity="0.35">
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-70 0" dur="16s" repeatCount="indefinite"/>
  </path>
</g>

<!-- ground -->
<line x1="76" y1="{y+220}" x2="924" y2="{y+220}" class="line" stroke-width="3"/>
<g stroke="var(--softline)" stroke-width="2">
  <line x1="108" y1="{y+228}" x2="148" y2="{y+228}">
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-70 0" dur="1.2s" repeatCount="indefinite"/>
  </line>
  <line x1="315" y1="{y+228}" x2="365" y2="{y+228}">
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-110 0" dur="1.6s" repeatCount="indefinite"/>
  </line>
  <line x1="620" y1="{y+228}" x2="690" y2="{y+228}">
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-130 0" dur="1.1s" repeatCount="indefinite"/>
  </line>
  <line x1="820" y1="{y+228}" x2="880" y2="{y+228}">
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-140 0" dur="0.95s" repeatCount="indefinite"/>
  </line>
</g>

<!-- phase labels -->
<text x="786" y="{y+92}" class="mono-xs">speed ×1.0</text>
<text x="786" y="{y+92}" class="mono-xs">
  <animate attributeName="opacity" values="0;1;0;0" keyTimes="0;.34;.35;1" dur="18s" repeatCount="indefinite"/>
  speed ×1.4
</text>
<text x="786" y="{y+92}" class="mono-xs">
  <animate attributeName="opacity" values="0;0;1;0" keyTimes="0;.66;.67;1" dur="18s" repeatCount="indefinite"/>
  speed ×1.8
</text>

<!-- dino runner -->
<g class="fg">
  <animateTransform attributeName="transform" type="translate"
    values="
      0 0;
      0 0;
      0 -34;
      0 -34;
      0 0;
      0 0;
      0 -42;
      0 -42;
      0 0;
      0 0;
      0 -36;
      0 -36;
      0 0;
      0 0;
      0 -48;
      0 -48;
      0 0;
      0 0;
      0 -36;
      0 -36;
      0 0;
      0 -44;
      0 -44;
      0 0;
      0 0"
    keyTimes="
      0.00;
      0.18;
      0.205;
      0.255;
      0.30;
      0.35;
      0.392;
      0.44;
      0.50;
      0.54;
      0.575;
      0.612;
      0.66;
      0.72;
      0.747;
      0.785;
      0.815;
      0.85;
      0.874;
      0.905;
      0.93;
      0.944;
      0.97;
      0.99;
      1.0"
    dur="18s" repeatCount="indefinite"/>
  <!-- body -->
  <rect x="155" y="{y+182}" width="24" height="26" fill="currentColor"/>
  <rect x="178" y="{y+188}" width="10" height="12" fill="currentColor"/>
  <rect x="149" y="{y+193}" width="8" height="8" fill="currentColor"/>
  <rect x="160" y="{y+170}" width="15" height="16" fill="currentColor"/>
  <rect x="171" y="{y+166}" width="8" height="8" fill="currentColor"/>
  <rect x="173" y="{y+174}" width="3" height="3" fill="var(--bg)"/>
  <rect x="187" y="{y+194}" width="3" height="14" fill="currentColor"/>
  <!-- arms -->
  <rect x="151" y="{y+197}" width="7" height="10" fill="currentColor">
    <animate attributeName="height" values="10;6;10;6;10" dur="0.33s" repeatCount="indefinite"/>
  </rect>
  <rect x="154" y="{y+206}" width="5" height="7" fill="currentColor"/>
  <!-- legs -->
  <rect x="160" y="{y+208}" width="7" height="14" fill="currentColor">
    <animate attributeName="height" values="14;8;14;8;14" dur="0.30s" repeatCount="indefinite"/>
  </rect>
  <rect x="171" y="{y+208}" width="7" height="14" fill="currentColor">
    <animate attributeName="height" values="8;14;8;14;8" dur="0.30s" repeatCount="indefinite"/>
  </rect>
</g>

<!-- slow obstacles -->
<g class="fg">
  <g>
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-1030 0" dur="5.4s" begin="0s" repeatCount="indefinite"/>
    <rect x="930" y="{y+192}" width="10" height="28" fill="currentColor"/>
    <rect x="942" y="{y+198}" width="9" height="22" fill="currentColor"/>
    <rect x="925" y="{y+201}" width="5" height="10" fill="currentColor"/>
    <rect x="939" y="{y+186}" width="4" height="9" fill="currentColor"/>
  </g>
  <g>
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-1030 0" dur="5.4s" begin="1.8s" repeatCount="indefinite"/>
    <rect x="930" y="{y+188}" width="11" height="32" fill="currentColor"/>
    <rect x="944" y="{y+196}" width="9" height="24" fill="currentColor"/>
    <rect x="925" y="{y+201}" width="5" height="10" fill="currentColor"/>
    <rect x="940" y="{y+182}" width="4" height="10" fill="currentColor"/>
  </g>
</g>

<!-- medium obstacles -->
<g class="fg" opacity="0">
  <animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;.33;.34;.66;1" dur="18s" repeatCount="indefinite"/>
  <g>
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-1040 0" dur="4.2s" begin="6.1s" repeatCount="indefinite"/>
    <rect x="930" y="{y+195}" width="8" height="25" fill="currentColor"/>
    <rect x="941" y="{y+187}" width="11" height="33" fill="currentColor"/>
    <rect x="924" y="{y+203}" width="5" height="8" fill="currentColor"/>
    <rect x="944" y="{y+181}" width="4" height="8" fill="currentColor"/>
  </g>
  <g>
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-1040 0" dur="4.2s" begin="7.55s" repeatCount="indefinite"/>
    <rect x="930" y="{y+192}" width="10" height="28" fill="currentColor"/>
    <rect x="943" y="{y+201}" width="8" height="19" fill="currentColor"/>
    <rect x="925" y="{y+201}" width="5" height="10" fill="currentColor"/>
    <rect x="940" y="{y+187}" width="4" height="8" fill="currentColor"/>
  </g>
</g>

<!-- fast obstacles -->
<g class="fg" opacity="0">
  <animate attributeName="opacity" values="0;0;0;1;1" keyTimes="0;.66;.67;.68;1" dur="18s" repeatCount="indefinite"/>
  <g>
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-1060 0" dur="3.1s" begin="12.1s" repeatCount="indefinite"/>
    <rect x="930" y="{y+195}" width="9" height="25" fill="currentColor"/>
    <rect x="942" y="{y+189}" width="10" height="31" fill="currentColor"/>
    <rect x="925" y="{y+204}" width="5" height="8" fill="currentColor"/>
  </g>
  <g>
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-1060 0" dur="3.1s" begin="13.12s" repeatCount="indefinite"/>
    <rect x="930" y="{y+190}" width="11" height="30" fill="currentColor"/>
    <rect x="944" y="{y+198}" width="8" height="22" fill="currentColor"/>
    <rect x="925" y="{y+200}" width="5" height="11" fill="currentColor"/>
  </g>
  <g>
    <animateTransform attributeName="transform" type="translate" from="0 0" to="-1060 0" dur="3.1s" begin="14.05s" repeatCount="indefinite"/>
    <rect x="930" y="{y+194}" width="8" height="26" fill="currentColor"/>
    <rect x="941" y="{y+185}" width="11" height="35" fill="currentColor"/>
    <rect x="944" y="{y+177}" width="4" height="8" fill="currentColor"/>
  </g>
</g>
"""

def build_svg(repos, contributions, avatar_uri, languages, private_capable):

    repo_count = len(repos)
    top_langs = list(languages.items())[:5]
    stack_items = []
    for lang, value in top_langs:
        if isinstance(value, int) and value > 50:
            shown = f"{value} bytes"
        else:
            shown = str(value)
        stack_items.append({"label": lang, "value": shown})
    stack_items.append({"label": "Repos", "value": str(repo_count)})

    W = 1000
    chart_y = 460
    chart_h = 360
    stack_y = chart_y + chart_h + 28
    stack_y_h = 252
    game_y = stack_y + stack_y_h + 28
    game_y_h = 294
    repos_y = game_y + game_y_h + 28

    row_h = 68
    repo_box_h = 92 + max(1, repo_count) * row_h
    H = repos_y + repo_box_h + 28

    out = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
  :root {{
    --bg:#ffffff; --panel:#f5f5f5; --panel2:#eeeeee;
    --fg:#111111; --muted:#5d5d5d; --line:#111111; --softline:#b7b7b7;
    --cell0:#ececec; --cell1:#c9c9c9; --cell2:#969696; --cell3:#5c5c5c; --cell4:#111111;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0d1117; --panel:#161b22; --panel2:#21262d;
      --fg:#f0f6fc; --muted:#8b949e; --line:#f0f6fc; --softline:#484f58;
      --cell0:#21262d; --cell1:#30363d; --cell2:#6e7681; --cell3:#b1bac4; --cell4:#f0f6fc;
    }}
  }}
  .bg{{fill:var(--bg)}} .panel{{fill:var(--panel)}} .panel2{{fill:var(--panel2)}}
  .fg{{fill:var(--fg);color:var(--fg)}} .muted{{fill:var(--muted)}}
  .line{{stroke:var(--line)}} .softline{{stroke:var(--softline)}}
  .title{{font:800 62px ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
  .section{{font:800 36px ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:var(--fg)}}
  .mono{{font:20px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;fill:var(--fg)}}
  .mono-sm{{font:16px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;fill:var(--fg)}}
  .mono-xs{{font:14px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;fill:var(--muted)}}
  .repo{{font:700 21px ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;fill:var(--fg)}}
  .pixel{{shape-rendering:crispEdges}}
</style>

<rect class="bg" width="{W}" height="{H}" rx="8"/>
<rect x="8" y="8" width="984" height="{H-16}" fill="none" class="line" stroke-width="3"/>
''']

    out.append(title_text(58, 150, "Hello."))
    out.append(title_text(58, 221, f"I’m {USERNAME}."))

    out.append(f'''
<text x="61" y="268" class="mono">I code, error happens, i sleep</text>
<text x="61" y="298" class="mono">like nothing happened.</text>

<rect x="60" y="336" width="238" height="56" class="panel2 line" stroke-width="2"/>
<text x="90" y="372" class="mono">Known as Werus</text>

<rect x="548" y="55" width="384" height="342" class="panel line" stroke-width="3"/>
<rect x="548" y="55" width="384" height="38" class="panel2 line" stroke-width="3"/>
<circle cx="896" cy="74" r="8" fill="none" class="line" stroke-width="2"/>
<circle cx="870" cy="74" r="8" fill="none" class="line" stroke-width="2"/>
<text x="566" y="80" class="mono-sm">{USERNAME}.exe</text>
<defs><clipPath id="avatarClip"><rect x="560" y="104" width="360" height="280" rx="2"/></clipPath></defs>
''')

    if avatar_uri:
        out.append(f'<image href="{avatar_uri}" x="560" y="104" width="360" height="280" preserveAspectRatio="xMidYMid slice" clip-path="url(#avatarClip)"/>')
    else:
        out.append('<rect x="560" y="104" width="360" height="280" class="panel2"/>')
    out.append('<rect x="560" y="104" width="360" height="280" fill="none" class="line" stroke-width="2"/>')

    out.append(f'''
<rect x="28" y="{chart_y}" width="944" height="{chart_h}" class="panel line" stroke-width="2.5"/>
<text x="58" y="{chart_y+58}" class="section">Contribution Chart</text>

<rect x="52" y="{chart_y+92}" width="896" height="224" class="bg line" stroke-width="2.5"/>
<rect x="52" y="{chart_y+92}" width="896" height="42" class="panel2 line" stroke-width="2.5"/>
<circle cx="77" cy="{chart_y+113}" r="7" fill="none" class="line" stroke-width="2"/>
<circle cx="100" cy="{chart_y+113}" r="7" fill="none" class="line" stroke-width="2"/>
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
                out.append(f'<text x="{x}" y="{chart_y+164}" class="mono-xs">{month}</text>')
            last_month = month

    for label, yy in [("Mon", chart_y+197), ("Wed", chart_y+227), ("Fri", chart_y+257)]:
        out.append(f'<text x="70" y="{yy}" class="mono-xs">{label}</text>')

    start_x, start_y, cell, gap = 122, chart_y + 178, 11, 4
    for c in range(53):
        week_start = first_sunday + timedelta(weeks=c)
        for r in range(7):
            day = week_start + timedelta(days=r)
            level = contributions.get(day.isoformat(), 0)
            out.append(f'<rect x="{start_x+c*(cell+gap)}" y="{start_y+r*(cell+gap)}" width="{cell}" height="{cell}" fill="var(--cell{level})" class="pixel"/>')

    out.append(f'''
<text x="70" y="{chart_y+298}" class="mono-xs">Less</text>
<rect x="122" y="{chart_y+286}" width="14" height="14" fill="var(--cell0)"/>
<rect x="144" y="{chart_y+286}" width="14" height="14" fill="var(--cell1)"/>
<rect x="166" y="{chart_y+286}" width="14" height="14" fill="var(--cell2)"/>
<rect x="188" y="{chart_y+286}" width="14" height="14" fill="var(--cell3)"/>
<rect x="210" y="{chart_y+286}" width="14" height="14" fill="var(--cell4)"/>
<text x="234" y="{chart_y+298}" class="mono-xs">More</text>
''')

    out.append(build_stack_panel(stack_items, repo_count, private_capable, stack_y))
    out.append(build_game_panel(game_y))

    out.append(f'''
<rect x="28" y="{repos_y}" width="944" height="{repo_box_h}" class="panel line" stroke-width="2.5"/>
<text x="58" y="{repos_y+58}" class="section">Repository List</text>
''')

    y0 = repos_y + 86
    if not repos:
        out.append(f'<text x="70" y="{y0+38}" class="mono">No repositories found.</text>')

    for i, repo in enumerate(repos):
        y = y0 + i * 68
        name = escape(repo.get("name", ""))
        lang = escape(repo.get("language") or "—")
        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        privacy = "private" if repo.get("private") else "public"

        out.append(f'<rect x="58" y="{y}" width="884" height="56" class="bg softline" stroke-width="1.5"/>')
        out.append(repo_icon(78, y + 18))
        out.append(f'<text x="112" y="{y+35}" class="repo">{name}</text>')
        out.append(f'<text x="582" y="{y+34}" class="mono-xs">{privacy}</text>')
        out.append(f'<text x="668" y="{y+34}" class="mono-xs">{lang}</text>')
        out.append(f'<text x="790" y="{y+34}" class="mono-xs">★ {stars}   ⑂ {forks}</text>')
        out.append(f'<rect x="885" y="{y+9}" width="42" height="38" class="panel2 line" stroke-width="1.5"/>')
        out.append(repo_icon(896, y + 19))

    out.append("</svg>")
    return "".join(out)


def write_readme(svg_text):
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
    repos, private_capable = get_repositories()
    languages = get_languages_breakdown(repos)
    contributions = get_contributions()
    avatar_uri = get_avatar_data_uri()

    try:
        PROFILE_SVG.unlink()
    except FileNotFoundError:
        pass

    svg_text = build_svg(repos, contributions, avatar_uri, languages, private_capable)
    PROFILE_SVG.write_text(svg_text, encoding="utf-8")
    write_readme(svg_text)

    print(
        f"Generated {PROFILE_SVG} and {README} from {len(repos)} repositories "
        f"({'including private' if private_capable else 'public only'})."
    )


if __name__ == "__main__":
    main()
