#!/usr/bin/env python3
"""
ingest_gc_csv.py -- identify and file GameChanger's filtered season CSVs.

The filtered export carries no date, no opponent and no game id. Two exports
from two different games are byte-distinguishable but not *nameable* -- you get
Stats.csv, Stats__1_.csv, Stats__2_.csv and no way back.

Rather than renaming by hand, this fingerprints each CSV against the games
already parsed out of box score PDFs. Every pitcher's (jersey, IP, pitch count)
triple is effectively unique per game, so the file identifies itself.

Usage:
    python3 ingest_gc_csv.py data/raw/gc_csv/*.csv \
        --pitching data/pitching_by_game.csv \
        --team LadyDukesWPA2033 \
        --outdir data/by_game/
"""

import argparse
import pathlib
import shutil
import sys

import pandas as pd

# The export has a two-row header: row 0 spans sections (Batting / Pitching /
# Fielding), row 1 has the real column names. Names repeat across sections --
# GP, H, R, BB, SO, HR, SB, CS all appear twice, and 2B/3B are batting stats in
# one place and fielding-position innings in another. Prefix by section.


def read_gc_csv(path):
    raw = pd.read_csv(path, header=None, dtype=str, encoding="utf-8-sig",
                      keep_default_na=False, na_filter=False)
    sections, cur = [], ""
    for v in raw.iloc[0]:
        v = (v or "").strip()
        if v:
            cur = v
        sections.append(cur)
    names = [str(n).strip() for n in raw.iloc[1]]
    cols = []
    for sec, name in zip(sections, names):
        cols.append(f"{sec}.{name}" if sec else name)
    df = raw.iloc[2:].reset_index(drop=True)
    df.columns = cols
    # The export ends with a "Totals" row that is not a player. Left in, it
    # pollutes the fingerprint and drags an exact match down to ~67%.
    df = df[df["Number"].str.strip().str.isdigit()].reset_index(drop=True)
    return df


def to_num(s):
    return pd.to_numeric(s.replace({"-": None, "N/A": None, "": None}), errors="coerce")


def fingerprint_csv(df):
    """{(jersey, IP, pitches)} for everyone who threw."""
    ip = to_num(df["Pitching.IP"])
    pitches = to_num(df["Pitching.#P"])
    out = set()
    for jersey, i, p in zip(df["Number"], ip, pitches):
        if pd.notna(i) and i > 0:
            out.add((str(jersey).strip(), float(i), int(p) if pd.notna(p) else -1))
    return out


def fingerprint_games(pitching_csv, team):
    p = pd.read_csv(pitching_csv)
    p = p[p["team"] == team]
    games = {}
    for gid, grp in p.groupby("game_id"):
        games[gid] = {
            (str(int(r.jersey)), float(r.IP),
             int(r.pitches) if pd.notna(r.pitches) else -1)
            for r in grp.itertuples()
        }
    return games


def score(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--pitching", default="data/pitching_by_game.csv")
    ap.add_argument("--team", required=True,
                    help="team name as it appears in the box score filenames")
    ap.add_argument("--outdir", default="data/by_game")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    games = fingerprint_games(args.pitching, args.team)
    if not games:
        sys.exit(f"no games for team {args.team!r} in {args.pitching}")

    out = pathlib.Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    used = {}

    for path in args.csvs:
        df = read_gc_csv(path)
        fp = fingerprint_csv(df)
        ranked = sorted(((score(fp, g), gid) for gid, g in games.items()),
                        reverse=True)
        best, gid = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0

        name = pathlib.Path(path).name
        if best < 0.5:
            print(f"  ?? {name}: no confident match (best {best:.0%} -> {gid})")
            continue
        if gid in used:
            print(f"  !! {name}: {gid} already claimed by {used[gid]} -- skipping")
            continue
        if best - runner_up < 0.2:
            print(f"  !! {name}: ambiguous ({best:.0%} vs {runner_up:.0%}) -- skipping")
            continue

        used[gid] = name
        dest = out / f"{gid}.csv"
        print(f"  ok {name}  ->  {dest.name}   (match {best:.0%})")
        if not args.dry_run:
            shutil.copy2(path, dest)


if __name__ == "__main__":
    main()
