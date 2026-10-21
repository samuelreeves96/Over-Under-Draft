# NBA Over/Under Tracker

Tracks our season win-total competition. Each pick scores the gap between the team's projected wins and the line: positive if the team is beating the line in the direction you picked, negative if not.

- **Win pace** projection = current win % × 82.
- **Efficiency** projection = current wins + remaining games × Pythagorean win % (points scored¹⁴ ÷ (points scored¹⁴ + points allowed¹⁴)).
- Before a team has played, its projection equals its line (0 points). Toggle between the two methods at the top of the page.
- **Points (Over)** = projected wins − line. **Points (Under)** = line − projected wins.

## Files

| File | What it is |
|---|---|
| `index.html` | The site (leaderboard + sortable picks table) |
| `picks.csv` | Everyone's picks: Round, Pick, Name, Over/Under, Team, Line |
| `data/standings.json` | Latest team records and points for/against, refreshed by the GitHub Action |
| `data/history.json` | One saved snapshot per day; drives the Movers panel and Progress charts |
| `scripts/fetch_standings.py` | Pulls standings from ESPN |
| `.github/workflows/update-standings.yml` | Runs the fetch twice a day and commits any changes |

The page also loads standings live from ESPN when it opens, falling back to the saved copy if that fails.

## Setup

1. Create a new GitHub repository and upload everything in this folder (keep the `.github` folder; it's hidden on Mac/Linux).
2. **Settings → Pages**: set Source to *Deploy from a branch*, Branch `main`, folder `/ (root)`.
3. **Actions → Update standings → Run workflow** to load live standings straight away. After that it runs automatically.
4. The site is at `https://samuelreeves96.github.io/Over-Under-Draft/`.

If the Action fails with a permissions error, go to **Settings → Actions → General → Workflow permissions** and choose *Read and write permissions*.

## Changing picks

Edit `picks.csv` on GitHub. Team names can be nicknames (e.g. `Blazers`, `Wolves`); if a name doesn't match, the site shows a warning and you can add it to `TEAM_ALIASES` in `index.html`.
