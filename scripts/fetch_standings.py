"""Fetch current NBA standings from ESPN and write data/standings.json.

Run by the GitHub Action in .github/workflows/update-standings.yml.
Uses only the Python standard library.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
OUT = Path(__file__).resolve().parent.parent / "data" / "standings.json"


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


def stat(entry, key):
    for s in entry.get("stats", []):
        if s.get("name") == key or s.get("type") == key:
            return int(round(float(s.get("value", 0))))
    return 0


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
        teams[name] = {
            "name": name,
            "fullName": team.get("displayName", name),
            "abbr": team.get("abbreviation", ""),
            "wins": stat(entry, "wins"),
            "losses": stat(entry, "losses"),
        }

    if len(teams) < 30:
        # Don't overwrite good data with a partial response.
        sys.exit(f"Expected 30 teams, got {len(teams)}; leaving standings.json unchanged.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "source": "ESPN",
        "teams": sorted(teams.values(), key=lambda t: t["name"]),
    }, indent=2) + "\n")
    print(f"Wrote {len(teams)} teams to {OUT}")


if __name__ == "__main__":
    main()
