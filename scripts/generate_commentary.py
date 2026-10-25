"""Write AI commentary on the current standings, in the voice of the group's commentary.

Reads picks.csv, data/standings.json and data/history.json, works out everyone's
scores (same maths as index.html), asks Claude for commentary, and saves it to
data/commentary.json for the site to show.

Needs an ANTHROPIC_API_KEY environment variable (a GitHub Actions secret).
Uses only the Python standard library.
"""
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MODEL = os.environ.get("COMMENTARY_MODEL", "claude-sonnet-5-5")
API_URL = "https://api.anthropic.com/v1/messages"
SEASON_GAMES = 82
PYTH_EXP = 14
LOOKBACK_DAYS = 7
ALIASES = {"blazers": "trail blazers", "wolves": "timberwolves", "76's": "76ers",
           "sixers": "76ers", "warrior": "warriors"}


def project(rec, line, method):
    wins, losses, pf, pa = rec
    gp = wins + losses
    if not gp:
        return line
    if method == "eff" and pf > 0 and pa > 0:
        pyth = 1 / (1 + (pa / pf) ** PYTH_EXP)
        return wins + max(0, SEASON_GAMES - gp) * pyth
    return wins / gp * SEASON_GAMES


def points(pick, rec, method):
    diff = project(rec, pick["line"], method) - pick["line"]
    return diff if pick["side"] == "Over" else -diff


def main():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("No ANTHROPIC_API_KEY set; skipping commentary.")
        return

    # Scheduled runs skip if an edition was written in the last 5 days, so a delayed or
    # duplicate scheduled run never replaces this week's commentary. Manual runs
    # ("Run workflow") always write a new one.
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        try:
            last = json.loads((DATA / "commentary.json").read_text()).get("date")
            if last and (date.today() - date.fromisoformat(last)).days < 5:
                print(f"This week's commentary already exists ({last}); skipping scheduled run.")
                return
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass

    picks = []
    with open(ROOT / "picks.csv", newline="") as f:
        for row in csv.DictReader(f):
            team = row["Team"].strip()
            picks.append({
                "name": row["Name"].strip(), "team": team,
                "key": ALIASES.get(team.lower(), team.lower()),
                "side": "Over" if row["Over/Under"].strip().lower() == "over" else "Under",
                "line": float(row["Line"]),
                "round": int(row["Round"]) if row.get("Round", "").strip() else None,
            })

    standings = json.loads((DATA / "standings.json").read_text())
    if standings.get("sample"):
        print("Standings are still placeholders; skipping commentary.")
        return
    now = {t["name"].lower(): (t["wins"], t["losses"], t.get("pointsFor", 0), t.get("pointsAgainst", 0))
           for t in standings["teams"]}
    if not any(w + l for w, l, *_ in now.values()):
        print("No games played yet; skipping commentary.")
        return

    # Snapshot from about a week ago, for "who's moved" commentary
    try:
        history = json.loads((DATA / "history.json").read_text()).get("days", [])
    except FileNotFoundError:
        history = []
    today = (datetime.now(timezone.utc) - timedelta(hours=10)).date()
    if history:
        today = max(today, date.fromisoformat(history[-1]["date"]))
    cutoff = today - timedelta(days=LOOKBACK_DAYS)
    past_days = [d for d in history if date.fromisoformat(d["date"]) <= cutoff]
    then = ({k.lower(): tuple(v) for k, v in past_days[-1]["teams"].items()} if past_days else {})
    zero = (0, 0, 0, 0)

    rows = []
    for p in picks:
        rec, old = now.get(p["key"], zero), then.get(p["key"], zero)
        rows.append({
            "player": p["name"], "round": p["round"], "pick": f'{p["team"]} {p["side"]} {p["line"]}',
            "record": f"{rec[0]}-{rec[1]}",
            "projected_wins_pace": round(project(rec, p["line"], "pace"), 1),
            "points_pace": round(points(p, rec, "pace"), 1),
            "points_efficiency": round(points(p, rec, "eff"), 1),
            "change_last_week": round(points(p, rec, "pace") - points(p, old, "pace"), 1),
        })

    players = {}
    for r in rows:
        pl = players.setdefault(r["player"], {"player": r["player"], "total": 0, "total_efficiency": 0,
                                              "change_last_week": 0, "picks": []})
        pl["total"] += r["points_pace"]
        pl["total_efficiency"] += r["points_efficiency"]
        pl["change_last_week"] += r["change_last_week"]
        pl["picks"].append({k: v for k, v in r.items() if k != "player"})
    ranked = sorted(players.values(), key=lambda x: -x["total"])
    for i, pl in enumerate(ranked, 1):
        pl["rank"] = i
        for k in ("total", "total_efficiency", "change_last_week"):
            pl[k] = round(pl[k], 1)

    games = [w + l for w, l, *_ in now.values()]
    summary = {
        "date": date.today().isoformat(),
        "games_played_per_team": f"{min(games)}-{max(games)} of 82",
        "comparison_window": f"change_last_week compares with {past_days[-1]['date']}" if past_days
                             else "change_last_week is since the start of the season",
        "leaderboard": ranked,
    }

    previous = ""
    prev_path = DATA / "commentary.json"
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text())
            previous = f"\n\nLast edition's headline, for continuity (don't repeat its jokes): {prev.get('headline', '')}"
        except json.JSONDecodeError:
            pass

    style = (ROOT / "scripts" / "commentary_style.md").read_text()
    prompt = (
        "Here are this week's standings as JSON.\n\n"
        f"{json.dumps(summary, indent=1)}{previous}\n\n"
        "Write this week's commentary. Reply with only a JSON object, no code fences:\n"
        '{"headline": "short punchy title", "intro": "2-3 sentences on the state of the comp",'
        ' "players": [{"name": "exactly as in the data", "text": "2-4 sentences"}],'
        ' "signoff": "one line"}\n'
        "Cover every player in leaderboard order."
    )

    def call(no_thinking):
        payload = {"model": MODEL, "max_tokens": 16000, "system": style,
                   "messages": [{"role": "user", "content": prompt}]}
        if no_thinking:
            # Newer models (e.g. Sonnet 5.5) think before answering by default, and that thinking
            # counts toward max_tokens. Commentary doesn't need it, so switch it off.
            payload["thinking"] = {"type": "between_tools"}
        req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.load(resp)

    try:
        reply = call(no_thinking=True)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code == 400 and "thinking" in detail:
            print("This model doesn't accept that thinking setting; retrying with its default.")
            reply = call(no_thinking=False)
        else:
            sys.exit(f"Claude API error {e.code}: {detail[:1000]}")

    blocks = reply.get("content", [])
    stop = reply.get("stop_reason")
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    if not text:
        if stop == "refusal":
            print("Claude declined to write this week's commentary; keeping the previous edition.")
            return
        sys.exit(f"Claude's reply had no text (stop_reason={stop}, blocks={[b.get('type') for b in blocks]}).")
    # Pull the JSON object out even if it's wrapped in code fences or a sentence
    m = re.search(r"\{.*\}", text, re.S)
    try:
        out = json.loads(m.group(0) if m else text)
    except json.JSONDecodeError:
        sys.exit(f"Claude's reply wasn't valid JSON (stop_reason={stop}):\n" + text[:2000])

    totals = {pl["player"]: pl for pl in ranked}
    out["players"] = [
        {"name": p["name"], "text": p["text"],
         "rank": totals.get(p["name"], {}).get("rank"), "total": totals.get(p["name"], {}).get("total")}
        for p in out.get("players", []) if p.get("name") and p.get("text")
    ]
    out["date"] = summary["date"]
    out["basis"] = "Win pace"
    out["model"] = MODEL
    prev_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote commentary: {out.get('headline')}")


if __name__ == "__main__":
    main()
