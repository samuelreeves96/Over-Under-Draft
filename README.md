# NBA Over/Under Tracker

Tracks our season win-total competition. Each pick scores the gap between the team's projected wins and the line: positive if the team is beating the line in the direction you picked, negative if not.

- **Projected wins** = current win % × 82. Before a team has played, its projection equals its line (0 points).
- **Points (Over)** = projected wins − line. **Points (Under)** = line − projected wins.

## Files

| File | What it is |
|---|---|
| `index.html` | The site (leaderboard + sortable picks table) |
| `picks.csv` | Everyone's picks: Round, Pick, Name, Over/Under, Team, Line |
| `data/standings.json` | Team win–loss records, refreshed by the GitHub Action |
| `scripts/fetch_standings.py` | Pulls standings from ESPN |
| `.github/workflows/update-standings.yml` | Runs the fetch twice a day and commits any changes |

## Setup

1. Create a new GitHub repository and upload everything in this folder (keep the `.github` folder; it's hidden on Mac/Linux).
2. **Settings → Pages**: set Source to *Deploy from a branch*, Branch `main`, folder `/ (root)`.
3. **Actions → Update standings → Run workflow** to load live standings straight away. After that it runs automatically.
4. The site is at `https://<your-username>.github.io/<repo-name>/`.

If the Action fails with a permissions error, go to **Settings → Actions → General → Workflow permissions** and choose *Read and write permissions*.

## Changing picks

Edit `picks.csv` on GitHub. Team names can be nicknames (e.g. `Blazers`, `Wolves`); if a name doesn't match, the site shows a warning and you can add it to `TEAM_ALIASES` in `index.html`.
