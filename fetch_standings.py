"""Fetch current NBA standings from ESPN.

Writes:
  data/standings.json - the latest snapshot
  data/history.json   - one snapshot per day, used for movers and progress charts

Run by the GitHub Action in .github/workflows/update-standings.yml.
Uses only the Python standard library.
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

URL = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
DATA = Path(__file__).resolve().parent.parent / "data"


def find_entries(node):
    """Walk the ESPN response and yield every standings entry, whatever the nesting."""
    if isinstance(node, dict):
        standings = node.get("standings")
        if isinstance(standings, dict) and isinstance(standings.get("entries"), list):
            yield from standings["entries"]
        for value in node.values():
            yield from find_entries(value)
    elif isinstance(node, list):
        for item in node:
            yield from find_entries(item)


def stat(entry, *keys):
    for key in keys:
        for s in entry.get("stats", []):
            if s.get("name") == key or s.get("type") == key:
                try:
                    return float(s.get("value", 0))
                except (TypeError, ValueError):
                    pass
    return None


def fetch_scoreboard():
    """Today's games, saved as a backup in case the site can't reach ESPN live."""
    try:
        req = urllib.request.Request(SCOREBOARD_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as e:  # the standings still matter more than the schedule
        print("Scoreboard unavailable:", e)
        return None
    events = []
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        st = (ev.get("status") or comp.get("status") or {}).get("type", {})
        teams = []
        for c in comp.get("competitors", []):
            t = c.get("team", {})
            score = c.get("score")
            if isinstance(score, dict):
                score = score.get("value")
            records = c.get("records") or []
            teams.append({
                "homeAway": c.get("homeAway", ""),
                "name": t.get("name") or t.get("shortDisplayName", ""),
                "abbr": t.get("abbreviation", ""),
                "color": t.get("color", ""),
                "score": float(score) if score not in (None, "") else None,
                "winner": bool(c.get("winner")),
                "record": records[0].get("summary", "") if records else "",
            })
        teams.sort(key=lambda t: 0 if t["homeAway"] == "away" else 1)
        events.append({
            "id": ev.get("id"), "date": ev.get("date", ""),
            "state": st.get("state", "pre"), "detail": st.get("shortDetail") or st.get("detail", ""),
            "completed": bool(st.get("completed")), "teams": teams,
        })
    return {"date": (data.get("day") or {}).get("date", ""), "events": events}


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    teams = {}
    for entry in find_entries(data):
        team = entry.get("team", {})
        name = team.get("name") or team.get("shortDisplayName")
        if not name:
            continue
        wins = int(stat(entry, "wins") or 0)
        losses = int(stat(entry, "losses") or 0)
        gp = wins + losses
        pf = stat(entry, "pointsFor")
        pa = stat(entry, "pointsAgainst")
        if pf is None and gp:
            pf = (stat(entry, "avgPointsFor") or 0) * gp
        if pa is None and gp:
            pa = (stat(entry, "avgPointsAgainst") or 0) * gp
        teams[name] = {
            "name": name,
            "fullName": team.get("displayName", name),
            "abbr": team.get("abbreviation", ""),
            "wins": wins,
            "losses": losses,
            "pointsFor": round(pf or 0, 1),
            "pointsAgainst": round(pa or 0, 1),
        }

    if len(teams) < 30:
        # Don't overwrite good data with a partial response.
        sys.exit(f"Expected 30 teams, got {len(teams)}; leaving data unchanged.")

    now = datetime.now(timezone.utc)
    DATA.mkdir(parents=True, exist_ok=True)
    out = {
        "updated": now.isoformat(timespec="minutes"),
        "source": "ESPN",
        "teams": sorted(teams.values(), key=lambda t: t["name"]),
    }
    scoreboard = fetch_scoreboard()
    if scoreboard:
        out["scoreboard"] = scoreboard
    (DATA / "standings.json").write_text(json.dumps(out, indent=2) + "\n")

    # History: one row per US game date (UTC minus 10h lands on the night's games).
    day = (now - timedelta(hours=10)).date().isoformat()
    hist_path = DATA / "history.json"
    try:
        history = json.loads(hist_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        history = {"days": []}
    snapshot = {
        "date": day,
        "teams": {t["name"]: [t["wins"], t["losses"], t["pointsFor"], t["pointsAgainst"]]
                  for t in teams.values()},
    }
    history["days"] = [d for d in history["days"] if d["date"] != day] + [snapshot]
    history["days"].sort(key=lambda d: d["date"])
    # Compact: one line per day keeps git diffs readable.
    lines = ",\n".join("    " + json.dumps(d, separators=(",", ":")) for d in history["days"])
    hist_path.write_text('{\n  "_format": "teams[name] = [wins, losses, pointsFor, pointsAgainst]",\n'
                         f'  "days": [\n{lines}\n  ]\n}}\n')
    print(f"Wrote {len(teams)} teams; history now has {len(history['days'])} days")


if __name__ == "__main__":
    main()
