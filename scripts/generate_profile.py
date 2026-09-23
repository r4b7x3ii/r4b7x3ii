import base64
import hashlib
import json
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path

USERNAME = "r4b7x3ii"
REPOSITORY = "r4b7x3ii/r4b7x3ii"

PROFILE_SVG = Path("profile.svg")
README = Path("README.md")

PROFILE_DATA_TOKEN = os.getenv("PROFILE_DATA_TOKEN")
API_TOKEN = PROFILE_DATA_TOKEN or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")


def request_bytes(url, *, method="GET", data=None, headers=None, token=None):
    h = {
        "User-Agent": f"{USERNAME}-profile-updater",
        "Accept": "*/*",
    }
    active_token = token or API_TOKEN
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
    repos = []
    private_capable = bool(PROFILE_DATA_TOKEN)

    if private_capable:
        page = 1
        while True:
            batch = request_json(
                "https://api.github.com/user/repos"
                f"?per_page=100&page={page}&sort=updated&visibility=all&affiliation=owner",
                token=PROFILE_DATA_TOKEN,
            )
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    else:
        page = 1
        while True:
            batch = request_json(
                f"https://api.github.com/users/{USERNAME}/repos"
                f"?per_page=100&page={page}&sort=updated&type=owner",
                token=None,
            )
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1

    repos = [
        repo for repo in repos
        if repo.get("owner", {}).get("login", "").lower() == USERNAME.lower()
    ]
    return repos, private_capable


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
    if not API_TOKEN:
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


def get_activity_levels():
    counts = {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    for page in range(1, 4):
        try:
            events = request_json(
                f"https://api.github.com/users/{USERNAME}/events/public?per_page=100&page={page}"
            )
        except Exception as exc:
            print(f"Activity data unavailable: {exc}")
            break
        if not events:
            break
        older = False
        for event in events:
            try:
                stamp = datetime.fromisoformat(event.get("created_at", "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if stamp < cutoff:
                older = True
                continue
            payload = event.get("payload") or {}
            amount = len(payload.get("commits") or []) or payload.get("size") or 1
            weight = min(4, int(amount)) if event.get("type") == "PushEvent" else 1
            key = stamp.date().isoformat()
            counts[key] = counts.get(key, 0) + weight
        if older or len(events) < 100:
            break
    return {day: (1 if count == 1 else 2 if count <= 3 else 3 if count <= 6 else 4)
            for day, count in counts.items()}


def heatmap(x, y, caption, levels, palette):
    out = [
        f'<rect x="{x}" y="{y}" width="420" height="230" class="bg line" stroke-width="2"/>',
        f'<rect x="{x}" y="{y}" width="420" height="42" class="panel2 line" stroke-width="2"/>',
        f'<circle cx="{x+24}" cy="{y+21}" r="7" fill="none" class="line" stroke-width="2"/>',
        f'<circle cx="{x+47}" cy="{y+21}" r="7" fill="none" class="line" stroke-width="2"/>',
        f'<text x="{x+73}" y="{y+27}" class="mono-sm">{escape(caption)}</text>',
    ]
    today = date.today()
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    first = sunday - timedelta(weeks=12)
    sx, sy = x + 72, y + 82
    last_month = None
    for week in range(13):
        base = first + timedelta(weeks=week)
        month = base.strftime("%b")
        if month != last_month:
            out.append(f'<text x="{sx+week*21}" y="{y+67}" class="mono-xs">{month}</text>')
            last_month = month
        for day_in_week in range(7):
            day = base + timedelta(days=day_in_week)
            level = max(0, min(4, int(levels.get(day.isoformat(), 0))))
            out.append(
                f'<rect x="{sx+week*21}" y="{sy+day_in_week*17}" width="15" height="13" '
                f'fill="var(--{palette}{level})" class="pixel"/>'
            )
    for label, row in [("Mon", 1), ("Wed", 3), ("Fri", 5)]:
        out.append(f'<text x="{x+18}" y="{sy+row*17+11}" class="mono-xs">{label}</text>')
    out.append(f'<text x="{x+18}" y="{y+218}" class="mono-xs">Less</text>')
    for level in range(5):
        out.append(
            f'<rect x="{x+62+level*20}" y="{y+207}" width="13" height="13" '
            f'fill="var(--{palette}{level})"/>'
        )
    out.append(f'<text x="{x+171}" y="{y+218}" class="mono-xs">More</text>')
    return "".join(out)


def build_calendar_panel(contributions, activity, y):
    return (
        f'<rect x="28" y="{y}" width="944" height="360" class="panel line" stroke-width="2.5"/>'
        f'<text x="58" y="{y+58}" class="section">Contribution / Activity</text>'
        f'<text x="772" y="{y+55}" class="mono-xs">last 90 days</text>'
        + heatmap(52, y+96, "contributions.exe", contributions, "cell")
        + heatmap(528, y+96, "activity.exe", activity, "act")
    )


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
    return f"""
<rect x="28" y="{y}" width="944" height="294" class="panel line" stroke-width="2.5"/>
<defs><clipPath id="skyClip"><rect x="53" y="{y+39}" width="894" height="220"/></clipPath></defs>
<g clip-path="url(#skyClip)">
  <rect x="52" y="{y+38}" width="896" height="222" fill="#dff4ff">
    <animate attributeName="fill" values="#dff4ff;#93c9f5;#111c3a;#0b1020;#93c9f5;#dff4ff" keyTimes="0;.20;.40;.64;.82;1" dur="24s" repeatCount="indefinite"/>
  </rect>
  <g>
    <animate attributeName="opacity" values="1;1;0;0;0;1" keyTimes="0;.21;.38;.65;.82;1" dur="24s" repeatCount="indefinite"/>
    <g>
      <animateTransform attributeName="transform" type="translate" values="0 8;0 -22;0 8" dur="24s" repeatCount="indefinite"/>
      <circle cx="770" cy="{y+115}" r="31" fill="#ffcf59"/>
      <g stroke="#ffcf59" stroke-width="3">
        <path d="M770 {y+67}v-12 M770 {y+163}v12 M722 {y+115}h-12 M818 {y+115}h12 M736 {y+81}l-8 -8 M804 {y+81}l8 -8 M736 {y+149}l-8 8 M804 {y+149}l8 8"/>
      </g>
    </g>
    <g fill="#fff" opacity=".85">
      <g>
        <animateTransform attributeName="transform" type="translate" values="-70 0;110 0;-70 0" dur="24s" repeatCount="indefinite"/>
        <path d="M190 {y+126}q12 -17 28 -5q9 -22 30 -13q17 3 22 21h-81z"/>
      </g>
      <g>
        <animateTransform attributeName="transform" type="translate" values="80 0;-80 0;80 0" dur="31s" repeatCount="indefinite"/>
        <path d="M465 {y+105}q11 -16 25 -5q8 -18 27 -12q16 4 20 20h-72z"/>
      </g>
    </g>
  </g>
  <g opacity="0">
    <animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;.29;.43;.72;.89;1" dur="24s" repeatCount="indefinite"/>
    <g>
      <animateTransform attributeName="transform" type="translate" values="0 12;0 -8;0 12" dur="24s" repeatCount="indefinite"/>
      <circle cx="770" cy="{y+116}" r="49" fill="#f6f7ec"/>
      <circle cx="790" cy="{y+96}" r="49" fill="#0b1020"/>
    </g>
    <g fill="#f8fbff">
      <g>
        <animateTransform attributeName="transform" type="translate" values="-18 6;22 -9;-18 6" dur="18s" repeatCount="indefinite"/>
        <circle cx="115" cy="{y+118}" r="2"><animate attributeName="opacity" values=".35;1;.35" dur="2.3s" repeatCount="indefinite"/></circle>
        <circle cx="218" cy="{y+170}" r="2.5"><animate attributeName="opacity" values="1;.4;1" dur="3.2s" repeatCount="indefinite"/></circle>
        <path d="M170 {y+123}v20 M160 {y+133}h20" stroke="#fff" stroke-width="2"/>
      </g>
      <g>
        <animateTransform attributeName="transform" type="translate" values="15 -7;-21 12;15 -7" dur="22s" repeatCount="indefinite"/>
        <circle cx="325" cy="{y+106}" r="2"><animate attributeName="opacity" values=".25;1;.25" dur="1.8s" repeatCount="indefinite"/></circle>
        <circle cx="410" cy="{y+183}" r="2.5"><animate attributeName="opacity" values="1;.2;1" dur="2.9s" repeatCount="indefinite"/></circle>
        <path d="M354 {y+149}v16 M346 {y+157}h16" stroke="#fff" stroke-width="2"/>
      </g>
      <g>
        <animateTransform attributeName="transform" type="translate" values="-12 -9;27 8;-12 -9" dur="26s" repeatCount="indefinite"/>
        <circle cx="520" cy="{y+119}" r="2"><animate attributeName="opacity" values=".3;1;.3" dur="3s" repeatCount="indefinite"/></circle>
        <circle cx="612" cy="{y+199}" r="2.5"><animate attributeName="opacity" values=".9;.2;.9" dur="2.4s" repeatCount="indefinite"/></circle>
        <path d="M563 {y+160}v18 M554 {y+169}h18" stroke="#fff" stroke-width="2"/>
      </g>
      <g>
        <animateTransform attributeName="transform" type="translate" values="10 8;-22 -12;10 8" dur="20s" repeatCount="indefinite"/>
        <circle cx="840" cy="{y+181}" r="2"><animate attributeName="opacity" values=".2;1;.2" dur="2.1s" repeatCount="indefinite"/></circle>
        <circle cx="899" cy="{y+109}" r="2.5"><animate attributeName="opacity" values="1;.3;1" dur="3.4s" repeatCount="indefinite"/></circle>
      </g>
    </g>
  </g>
  <path d="M53 {y+219} C128 {y+197} 196 {y+241} 269 {y+219} S410 {y+197} 480 {y+219} S620 {y+241} 690 {y+219} S829 {y+197} 947 {y+219} L947 {y+261} L53 {y+261}Z" fill="#568ab0" opacity=".76">
    <animate attributeName="d" dur="3.5s" repeatCount="indefinite"
      values="M53 {y+219} C128 {y+197} 196 {y+241} 269 {y+219} S410 {y+197} 480 {y+219} S620 {y+241} 690 {y+219} S829 {y+197} 947 {y+219} L947 {y+261} L53 {y+261}Z;
              M53 {y+219} C128 {y+241} 196 {y+197} 269 {y+219} S410 {y+241} 480 {y+219} S620 {y+197} 690 {y+219} S829 {y+241} 947 {y+219} L947 {y+261} L53 {y+261}Z;
              M53 {y+219} C128 {y+197} 196 {y+241} 269 {y+219} S410 {y+197} 480 {y+219} S620 {y+241} 690 {y+219} S829 {y+197} 947 {y+219} L947 {y+261} L53 {y+261}Z"/>
  </path>
  <path d="M53 {y+235} C128 {y+220} 196 {y+252} 269 {y+235} S410 {y+220} 480 {y+235} S620 {y+252} 690 {y+235} S829 {y+220} 947 {y+235}" fill="none" stroke="#b7e4ff" stroke-width="2" opacity=".7">
    <animate attributeName="d" dur="4.1s" repeatCount="indefinite"
      values="M53 {y+235} C128 {y+220} 196 {y+252} 269 {y+235} S410 {y+220} 480 {y+235} S620 {y+252} 690 {y+235} S829 {y+220} 947 {y+235};
              M53 {y+235} C128 {y+252} 196 {y+220} 269 {y+235} S410 {y+252} 480 {y+235} S620 {y+220} 690 {y+235} S829 {y+252} 947 {y+235};
              M53 {y+235} C128 {y+220} 196 {y+252} 269 {y+235} S410 {y+220} 480 {y+235} S620 {y+252} 690 {y+235} S829 {y+220} 947 {y+235}"/>
  </path>
</g>
<rect x="52" y="{y+38}" width="896" height="222" fill="none" class="line" stroke-width="2.5"/>
"""


def build_svg(repos, contributions, activity, avatar_uri, languages, private_capable):
    repo_count = len(repos)
    top_langs = list(languages.items())[:5]
    stack_items = []
    for lang, value in top_langs:
        shown = f"{value} bytes" if isinstance(value, int) and value > 50 else str(value)
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
    --act0:#e6f2ff; --act1:#a8d9ff; --act2:#67b7ff; --act3:#267bf1; --act4:#0c3b87;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0d1117; --panel:#161b22; --panel2:#21262d;
      --fg:#f0f6fc; --muted:#8b949e; --line:#f0f6fc; --softline:#484f58;
      --cell0:#21262d; --cell1:#30363d; --cell2:#6e7681; --cell3:#b1bac4; --cell4:#f0f6fc;
      --act0:#18283d; --act1:#1b4479; --act2:#246db8; --act3:#58a6ff; --act4:#a5d4ff;
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

    out.append(build_calendar_panel(contributions, activity, chart_y))

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
    activity = get_activity_levels()
    avatar_uri = get_avatar_data_uri()

    try:
        PROFILE_SVG.unlink()
    except FileNotFoundError:
        pass

    svg_text = build_svg(repos, contributions, activity, avatar_uri, languages, private_capable)
    build_id = os.getenv("GITHUB_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    svg_text = svg_text.replace("</svg>", f'<metadata id="build">{escape(build_id)}</metadata></svg>')
    PROFILE_SVG.write_text(svg_text, encoding="utf-8")
    write_readme(svg_text)

    print(
        f"Generated {PROFILE_SVG} and {README} from {len(repos)} repositories "
        f"({'including private' if private_capable else 'public only'})."
    )


if __name__ == "__main__":
    main()
