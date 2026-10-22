"""Injury tracking for the over/under tracker.

Pulls ESPN's NBA injury report, each listed player's season stats and their team's
remaining schedule, and estimates each player's box plus/minus (BPM) from box-score
stats. Called from fetch_standings.py; the result is saved inside data/standings.json.

The BPM estimate uses the published Basketball-Reference BPM 2.0 regression
(per-100-possession box-score terms with position and offensive-role interpolation),
with league-average team context in place of each team's actual totals. The final
team adjustment (each team's rating shared across its players) is applied in the page,
using the team's current rating. Uses only the Python standard library.
"""
import json
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
SCHEDULE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{tid}/schedule?seasontype=2"
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
STATS_URL = CORE + "/seasons/{season}/types/2/athletes/{aid}/statistics"

PRIOR_MINUTES = 800        # how much last season counts while this season's sample is small
SEASON_RE = re.compile(r"(rest|remainder) of the (season|year)|season[- ]ending|out for the season", re.I)

# League-average team context, per game (recent seasons) and pace of ~100 possessions
PACE = 100.0
TEAM = dict(trb=44.0, stl=8.0, pf=19.0, ast=27.0, blk=5.0, pts=115.0, fga=89.0, fta=22.0)
_THRESH = TEAM["pts"] / (TEAM["fga"] + 0.44 * TEAM["fta"]) - 0.33
_TEAM_THRESH_PTS = TEAM["pts"] - _THRESH * (TEAM["fga"] + 0.44 * TEAM["fta"])


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def season_year(today):
    """ESPN labels a season by the year it ends (2026-27 -> 2027)."""
    return today.year + 1 if today.month >= 8 else today.year


def athlete_id(a):
    if a.get("id"):
        return str(a["id"])
    for text in [a.get("uid", ""), a.get("$ref", "")] + [l.get("href", "") for l in a.get("links", [])]:
        m = re.search(r"(?:/id/|athletes/|~a:)(\d+)", text or "")
        if m:
            return m.group(1)
    return None


def classify(status, comment):
    s = (status or "").lower()
    if "out" in s:
        return "season" if SEASON_RE.search(comment or "") or "season" in s else "out"
    if any(k in s for k in ("day-to-day", "day to day", "questionable", "doubtful")):
        return "dtd"
    return None  # probable / available: not counted


def core_stats(js):
    out = {}
    for cat in (js.get("splits") or {}).get("categories", []):
        for st in cat.get("stats", []):
            if st.get("name") is not None and st.get("value") is not None:
                out[st["name"]] = float(st["value"])
    gp = out.get("gamesPlayed", 0.0)

    def tot(name):
        if name in out:
            return out[name]
        avg = "avg" + name[0].upper() + name[1:]
        return out.get(avg, 0.0) * gp

    keys = ["minutes", "points", "threePointFieldGoalsMade", "fieldGoalsAttempted", "freeThrowsAttempted",
            "offensiveRebounds", "defensiveRebounds", "assists", "steals", "blocks", "turnovers", "fouls"]
    return {"gp": gp, **{k: tot(k) for k in keys}}


def _lerp(a, b, t):
    return a + (b - a) * t


def raw_bpm(s):
    """BPM 2.0 box-score terms with league-average team context (no team adjustment)."""
    mins = s["minutes"]
    if mins <= 0:
        return None
    k = 48.0 / mins * (100.0 / PACE)   # per 100 team possessions while on court
    pts, tpm, ast = s["points"] * k, s["threePointFieldGoalsMade"] * k, s["assists"] * k
    tov, orb, drb = s["turnovers"] * k, s["offensiveRebounds"] * k, s["defensiveRebounds"] * k
    stl, blk, pf = s["steals"] * k, s["blocks"] * k, s["fouls"] * k
    fga, fta = s["fieldGoalsAttempted"] * k, s["freeThrowsAttempted"] * k
    # Position (1 = point guard ... 5 = centre) and offensive role (1 = creator ... 5 = receiver),
    # each blended with 50 minutes of a neutral value for small samples
    pos = (2.130 + 8.668 * (orb + drb) / TEAM["trb"] - 2.486 * stl / TEAM["stl"] + 0.992 * pf / TEAM["pf"]
           - 3.536 * ast / TEAM["ast"] + 1.667 * blk / TEAM["blk"])
    pos = min(5.0, max(1.0, (pos * mins + 3.0 * 50) / (mins + 50)))
    thresh_pts = pts - _THRESH * (fga + 0.44 * fta)
    role = 6.00 - 6.642 * ast / TEAM["ast"] - 8.544 * thresh_pts / _TEAM_THRESH_PTS
    role = min(5.0, max(1.0, (role * mins + 4.0 * 50) / (mins + 50)))
    tp, tr = (pos - 1) / 4, (role - 1) / 4
    b = (0.860 * pts + 0.389 * tpm + _lerp(0.580, 1.034, tp) * ast - 0.964 * tov + _lerp(0.613, 0.181, tp) * orb
         + _lerp(0.116, 0.181, tp) * drb + _lerp(1.369, 1.008, tp) * stl + _lerp(1.327, 0.703, tp) * blk - 0.367 * pf
         + _lerp(-0.560, -0.780, tr) * fga + _lerp(-0.246, -0.343, tr) * fta)
    b += -0.818 * max(0.0, (3 - pos) / 2) + 2.774 * (role - 3) / 2
    return b + BPM_CALIBRATION


# Shift so a league-average stat line (one fifth of an average team) comes out at 0
BPM_CALIBRATION = 0.0
_avg = {k: v * 82 for k, v in dict(minutes=48, points=23, threePointFieldGoalsMade=2.6, assists=5.4, turnovers=2.8,
        offensiveRebounds=2.2, defensiveRebounds=6.6, steals=1.6, blocks=1.0, fouls=3.8,
        fieldGoalsAttempted=17.8, freeThrowsAttempted=4.4).items()}
BPM_CALIBRATION = -raw_bpm(_avg)


def estimate(aid, season, log):
    """Box BPM, blended with last season's while this season's sample is small."""
    parts = []
    for yr in (season, season - 1):
        try:
            s = core_stats(get_json(STATS_URL.format(season=yr, aid=aid)))
        except Exception as e:
            log(f"  stats {aid} {yr}: {e}")
            continue
        b = raw_bpm(s)
        if b is not None:
            parts.append((yr, s, b))
        if yr == season and s["minutes"] >= 1500:
            break  # plenty of this-season data
        time.sleep(0.15)
    if not parts:
        return None
    cur = next((p for p in parts if p[0] == season), None)
    prev = next((p for p in parts if p[0] == season - 1), None)
    w_cur = cur[1]["minutes"] if cur else 0.0
    w_prev = min(prev[1]["minutes"], PRIOR_MINUTES) if prev else 0.0
    if w_cur + w_prev <= 0:
        return None
    bpm = ((cur[2] * w_cur if cur else 0.0) + (prev[2] * w_prev if prev else 0.0)) / (w_cur + w_prev)
    bpm = max(-10.0, min(15.0, bpm))  # cap small-sample extremes
    src = cur if cur and cur[1]["gp"] > 0 else prev
    mpg = src[1]["minutes"] / src[1]["gp"] if src and src[1]["gp"] else 0.0
    return {
        "bpm": round(bpm, 1),
        "mpg": round(mpg, 1),
        "gp": int(cur[1]["gp"]) if cur else 0,
        "basis": "this season" if not prev or w_prev == 0 else ("last season" if not cur or w_cur == 0 else "blend"),
    }


def update_injuries(teams, previous, log=print):
    """teams: standings dict name -> {fullName, wins, losses, pointsAgainst}. previous: last saved injuries block."""
    today = datetime.now(timezone.utc) - timedelta(hours=10)   # US game date
    today_s = today.date().isoformat()
    season = season_year(today.date())
    by_full = {t["fullName"].lower(): name for name, t in teams.items()}
    prev = previous if previous and previous.get("season") == season else {"players": {}, "returned": {}}

    data = get_json(INJURIES_URL)
    current, team_ids = {}, {}
    for blk in data.get("injuries") or data.get("teams") or []:
        bteam = blk.get("team") or {}
        full = (blk.get("displayName") or bteam.get("displayName") or "").lower()
        for inj in blk.get("injuries", []):
            a = inj.get("athlete") or {}
            t_full = (full or ((a.get("team") or {}).get("displayName") or "")).lower()
            team = by_full.get(t_full)
            aid = athlete_id(a)
            if not team or not aid:
                continue
            team_ids[team] = str(blk.get("id") or bteam.get("id") or (a.get("team") or {}).get("id") or "")
            details = inj.get("details") or {}
            comment = " ".join(filter(None, [inj.get("shortComment"), inj.get("longComment")]))
            status_text = inj.get("status") or (inj.get("type") or {}).get("description") or ""
            kind = classify(status_text, comment)
            if not kind:
                continue
            injury = " ".join(filter(None, [details.get("side") if details.get("side") not in (None, "Not Specified") else None,
                                            details.get("type"), details.get("detail")])) or ""
            current[aid] = {
                "id": aid, "name": a.get("displayName") or a.get("fullName") or "",
                "short": a.get("shortName") or a.get("displayName") or "",
                "pos": (a.get("position") or {}).get("abbreviation", ""),
                "team": team, "status": kind, "label": status_text, "injury": injury,
                "comment": inj.get("shortComment") or "", "since": (inj.get("date") or "")[:10] or None,
                "returnDate": (details.get("returnDate") or "")[:10] or None,
            }

    # Dated log of who went out and who came back, for the progress charts
    events = list(prev.get("events", []))
    last_kind, last_date = {}, {}
    for e in events:                                   # stored oldest first
        last_kind[e["id"]], last_date[e["id"]] = e["kind"], e["date"]
    def log_event(p, kind, when):
        when = max(when, last_date.get(p["id"], ""))   # a player's events always run forward in time
        events.append({"date": when, "kind": kind, "id": p["id"], "name": p["name"], "short": p.get("short") or p["name"], "team": p["team"]})
        last_kind[p["id"]], last_date[p["id"]] = kind, when
    for aid, p in current.items():
        if p["status"] not in ("out", "season"):
            continue
        lk = last_kind.get(aid)
        if lk in (None, "returned"):                      # newly out (or hurt again)
            log_event(p, p["status"], p.get("since") or today_s)
        elif lk == "out" and p["status"] == "season":     # ruled out for the season
            log_event(p, "season", today_s)

    # Players who were out and have dropped off the report have returned
    returned = dict(prev.get("returned", {}))
    for aid, p in prev.get("players", {}).items():
        if p.get("status") in ("out", "season") and aid not in current:
            returned[aid] = {**p, "status": "returned", "returnedOn": today_s}
            log_event(p, "returned", today_s)
    for aid in list(returned):
        if aid in current:
            del returned[aid]  # hurt again

    # Stats for everyone we're tracking
    for group in (current, returned):
        for aid, p in list(group.items()):
            est = estimate(aid, season, log)
            t = teams.get(p["team"], {})
            p["teamGp"] = t.get("wins", 0) + t.get("losses", 0)
            p.pop("ws48", None)
            if est:
                p.update(est)
            else:
                p.setdefault("bpm", None)
            time.sleep(0.1)

    # Drop returns whose effect has worn off (they've now played nearly every game)
    for aid, p in list(returned.items()):
        tg = p.get("teamGp") or 0
        if tg and p.get("gp", 0) / tg >= 0.97:
            del returned[aid]

    # Remaining schedule for teams with an expected return date
    schedules = {}
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    for team in sorted({p["team"] for p in current.values() if p.get("returnDate")}):
        tid = team_ids.get(team)
        if not tid:
            continue
        try:
            ev = get_json(SCHEDULE_URL.format(tid=tid)).get("events", [])
            schedules[team] = sorted(e.get("date", "")[:16] for e in ev if (e.get("date") or "")[:16] >= now_iso)
        except Exception as e:
            log(f"  schedule {team}: {e}")
        time.sleep(0.1)

    log(f"Injuries: {len(current)} on the report, {len(returned)} returned")
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "season": season,
        "players": current,
        "returned": returned,
        "schedules": schedules,
        "events": sorted(events, key=lambda e: e["date"]),
    }
