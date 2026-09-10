# WPA2033

Opponent scouting catalog for Lady Dukes WPA 2033.

## The two streams

GameChanger gives a parent/manager account two artifacts, and they are good at
opposite things. The catalog needs both.

| | Filtered season CSV (web) | Box score PDF (mobile) |
|---|---|---|
| Covers | **Your team only** | **Both teams** |
| Depth | ~190 columns — QAB%, BABIP, pitch-type splits, first-pitch-strike % | AB/R/H/RBI/BB/SO, IP/H/R/ER/BB/SO/HR, plus a notes line |
| Per game? | Only if you filter to one game before exporting | Always — one PDF per game |
| Game identity | **Not in the file** — no date, no opponent, no game id | In the filename and the header |

The consequence: **opponent data comes from the PDFs, not the CSVs.** The season
CSV is the deep record of our own hitters. The box score is the only thing that
carries the other team's line, and it's the file that actually knows which game
it is.

## Layout

```
WPA2033/
├── scripts/
│   └── parse_boxscore.py       # PDF -> normalized rows (both teams)
├── data/
│   ├── raw/
│   │   ├── boxscores/          # PDFs, unrenamed from GameChanger
│   │   └── gc_csv/             # filtered exports, renamed to the game_id
│   ├── batting_by_game.csv     # one row per player per game
│   └── pitching_by_game.csv
└── README.md
```

## Ingesting a game

Drop the PDF into `data/raw/boxscores/` **without renaming it** — the parser
reads the game identity out of GameChanger's filename:

```
TeamA_vs_TeamB_Mon_D_YYYY.pdf
```

Then:

```bash
python3 scripts/parse_boxscore.py data/raw/boxscores/*.pdf --outdir data/
```

`TeamA` (first in the filename) is the left-hand table on the page. Verified
against both Sep 6 2026 scrimmages.

## Schema

`batting_by_game.csv`

| column | notes |
|---|---|
| `game_id` | `YYYY-MM-DD_TeamA_vs_TeamB` — the join key |
| `date`, `team`, `opponent` | |
| `player`, `jersey`, `pos` | |
| `AB R H RBI BB SO` | from the table |
| `2B 3B HR SB CS HBP SF E` | from the notes block under the table |

`pitching_by_game.csv`

| column | notes |
|---|---|
| `game_id`, `date`, `team`, `opponent` | |
| `player`, `jersey` | |
| `IP H R ER BB SO HR` | from the table |
| `pitches`, `strikes` | parsed out of the `P-S:` note |
| `BF` | parsed out of the `BF:` note |
| `decision` | `W` / `L` / `SV` |

## Gotchas the parser already handles

- **Jersey number is the key, not the name.** GameChanger ellipsis-truncates
  long names in the table cells, and the truncation point varies by game —
  `C McWilli` in one box score, `C McWill` in the next, `L Bruck` in the
  pitching table but `L Bruckner` in the notes line three inches below.
- **Two naming conventions.** Some teams score as `S Chimino`, others as
  `Bella H`. The surname isn't reliably the last token, so name matching
  compares the longest token.
- **Notes blocks wrap.** `E: S Chimino, M Jackson, B Schmidt` can break across
  two visual lines; the continuation line carries no `KEY:` of its own.
- **Duplicate column names in the season CSV.** `2B` and `3B` appear as batting
  stats *and* again at the end as fielding-position innings. Don't index by name
  without disambiguating the section from the two-row header.

## Privacy

The PDFs are already first-initial-plus-last-name — GameChanger does that for
you, so the opponent side of this repo carries no full names. The season CSV
does have full first names for our own roster. Keep `data/raw/gc_csv/` out of
any public commit, or strip the `First` column on ingest.
