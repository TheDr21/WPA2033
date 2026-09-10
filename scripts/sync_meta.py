#!/usr/bin/env python3
"""Add a row to data/game_meta.csv for any game that doesn't have one yet.

Never overwrites what's already there -- game_type is hand-maintained, because
nothing in a GameChanger box score says whether a game counted.
"""
import pathlib
import pandas as pd

COLS = ["game_id", "game_type", "event", "opponent_org", "notes"]
d = pathlib.Path("data")
games = pd.read_csv(d / "games.csv")
path = d / "game_meta.csv"

existing = pd.read_csv(path).fillna("") if path.exists() else pd.DataFrame(columns=COLS)
known = set(existing.get("game_id", []))
new = [{"game_id": g, "game_type": "", "event": "", "opponent_org": "", "notes": ""}
       for g in sorted(set(games["game_id"]) - known)]

if new:
    out = pd.concat([existing, pd.DataFrame(new)], ignore_index=True)[COLS]
    out.to_csv(path, index=False)
    print(f"added {len(new)} game(s) to game_meta.csv -- set game_type on each")
else:
    print("game_meta.csv already covers every game")
