# NBA Over/Under Tracker

Tracks our season win-total competition. Each pick scores the gap between the team's projected wins and the line: positive if the team is beating the line in the direction you picked, negative if not.

- **Win pace** projection = current win % × 82.
- **Efficiency** projection = current wins + remaining games × Pythagorean win % (points scored¹⁴ ÷ (points scored¹⁴ + points allowed¹⁴)).
- **Blended** projection = current wins + remaining games × win rate from the team's estimated true point margin, which starts at the margin the preseason line implies and shifts toward the margin actually played (the line counts as about 17 games of evidence; each point of margin ≈ 2.7 wins a season).
- Before a team has played, its projection equals its line (0 points). Toggle between the three methods at the top of the page.
- **Points (Over)** = projected wins − line. **Points (Under)** = line − projected wins.

## Files

| File | What it is |
|---|---|
| `index.html` | The site (leaderboard + sortable picks table) |
| `picks.csv` | Everyone's picks: Round, Pick, Name, Over/Under, Team, Line |
| `avatars/` | Profile pictures; mapped to names in `AVATARS` near the top of the script in `index.html` |
| `data/standings.json` | Latest team records and points for/against, refreshed by the GitHub Action |
| `data/history.json` | One saved snapshot per day; drives the Movers panel and Progress charts |
| `scripts/fetch_standings.py` | Pulls standings, today's games and injuries from ESPN |
| `scripts/injuries.py` | Reads ESPN's injury report, estimates each player's box plus/minus (BPM) and tracks injuries and returns (saved into `data/standings.json`) |
| `.github/workflows/update-standings.yml` | Runs the fetch twice a day and commits any changes |
| `scripts/generate_commentary.py` | Asks Claude for this week's commentary and saves it to `data/commentary.json` |
| `scripts/commentary_style.md` | The voice and rules the commentary is written to – edit this to change the tone |
| `.github/workflows/commentary.yml` | Writes new commentary every Monday morning (Sydney time) |

The page also loads standings and the day's games live from ESPN when it opens, falling back to the saved copy if that fails. Live scores refresh every minute while games are on. While games are live, the **If games ended now** switch counts them as finished with the current leader winning, across the whole page; switch it off for the official standings.

## Setup

1. Create a new GitHub repository and upload everything in this folder (keep the `.github` folder; it's hidden on Mac/Linux).
2. **Settings → Pages**: set Source to *Deploy from a branch*, Branch `main`, folder `/ (root)`.
3. **Actions → Update standings → Run workflow** to load live standings straight away. After that it runs automatically.
4. The site is at `https://<your-username>.github.io/<repo-name>/`.

If the Action fails with a permissions error, go to **Settings → Actions → General → Workflow permissions** and choose *Read and write permissions*.

## Changing picks

Edit `picks.csv` on GitHub. Team names can be nicknames (e.g. `Blazers`, `Wolves`); if a name doesn't match, the site shows a warning and you can add it to `TEAM_ALIASES` in `index.html`.

## AI commentary

The site shows weekly AI-written commentary in the group's usual style, with an **AI commentary** switch at the top to hide it (each viewer's choice is remembered in their browser).

To turn it on:

1. Get an API key from the [Claude Console](https://console.anthropic.com/) (you'll need to add a little credit; a weekly write-up costs a few cents).
2. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**. Name it `ANTHROPIC_API_KEY` and paste the key.
3. Go to **Actions → Weekly commentary → Run workflow** to write the first edition. After that it runs every Monday.

Without the secret, the workflow skips the commentary step and the site simply hides the panel. Note the repo is public, so anything in `scripts/commentary_style.md` is visible to anyone.

## Injuries

The **Injuries** section lists confirmed outs from ESPN's injury report and players returning from injury, and estimates how many wins each one adds to or takes off his team's projection. **Adjust for injuries** in the toolbar applies those estimates across the whole page, for whichever projection method is selected.

- **Player rating:** box plus/minus (BPM), estimated from ESPN box-score stats with Basketball-Reference's published BPM 2.0 formula using league-average team context, blended with last season while this season's sample is small, plus his team's rating ÷ 5 (a stand-in for BPM's team adjustment).
- **Value per game:** (BPM + 2) × share of minutes × 2.7 ÷ 82 wins, where −2 is replacement level, with a boost of up to 20% for stars.
- **Impact:** value per game × games left × (expected availability from here − availability the projection already assumes). Healthy players are expected to play 92% of games.
- **What the projection assumes:** win pace and efficiency assume he keeps playing as often as he has so far. Blended also leans on the preseason line, which assumed normal availability unless he was already hurt before the lines were set (`LINE_DATE` in `index.html`), so those injuries aren't counted twice.
- **Games missed:** a return date counts the team's games before it; out for the season, all remaining games; no return date, a typical layoff for that kind of injury; day-to-day, questionable or doubtful, half a game.
- Each run of the Action logs dated injury and return events, which appear as dots on the Progress charts.
