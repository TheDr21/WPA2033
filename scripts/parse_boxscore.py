#!/usr/bin/env python3
"""
parse_boxscore.py -- turn a GameChanger box score PDF into normalized rows.

The box score PDF is the only GameChanger artifact that contains BOTH teams.
That makes it the opponent-data stream. The filtered season CSV is deeper but
covers only your own roster.

Layout facts this relies on (verified against Sep 2026 exports):
  * Two side-by-side tables. Left column = first team named in the filename.
  * GameChanger names files  TeamA_vs_TeamB_Mon_D_YYYY.pdf
  * Player cells are already first-initial + last name ("S Chimino #4 (2B)").
  * Long names are ellipsis-truncated; the jersey number is the stable key.

Usage:
    python3 parse_boxscore.py <pdf> [<pdf> ...] --outdir data/
"""

import argparse
import pathlib
import re
import sys
from collections import defaultdict

import pdfplumber

# --------------------------------------------------------------------------
# filename -> game identity
# --------------------------------------------------------------------------

FNAME_RE = re.compile(
    r"^(?P<left>.+?)_vs_(?P<right>.+?)_(?P<mon>[A-Z][a-z]{2})_(?P<day>\d{1,2})_(?P<year>\d{4})$"
)

MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1)}


def parse_filename(path):
    m = FNAME_RE.match(pathlib.Path(path).stem)
    if not m:
        raise ValueError(
            f"{path}: filename does not match TeamA_vs_TeamB_Mon_D_YYYY.pdf"
        )
    g = m.groupdict()
    date = f"{g['year']}-{MONTHS[g['mon']]:02d}-{int(g['day']):02d}"
    return g["left"], g["right"], date


# --------------------------------------------------------------------------
# word extraction / row assembly
# --------------------------------------------------------------------------

def rows_by_column(page, y0, y1, mid_x, y_tol=3.0):
    """Return (left_rows, right_rows); each row is a list of words sorted by x."""
    buckets = {"L": defaultdict(list), "R": defaultdict(list)}
    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        if not (y0 <= w["top"] < y1):
            continue
        side = "L" if w["x0"] < mid_x else "R"
        # snap to a row key so cells on the same visual line group together
        key = round(w["top"] / y_tol)
        buckets[side][key].append(w)

    out = []
    for side in ("L", "R"):
        rows = []
        for key in sorted(buckets[side]):
            words = sorted(buckets[side][key], key=lambda w: w["x0"])
            rows.append(words)
        out.append(rows)
    return out


def row_text(words):
    return " ".join(w["text"] for w in words)


NUM = re.compile(r"^-?\d+(?:\.\d+)?$")
JERSEY = re.compile(r"#(\d+)")
POS = re.compile(r"\(([A-Z0-9]{1,3})\)")
JUNK = re.compile(r"[\u2026\u00a0]")


def split_name_and_nums(words, n_expected):
    """Split a table row into (name, jersey, pos, [numbers]).

    Returns None if the row doesn't carry a full stat line -- this filters out
    the stray glyphs that ellipsis truncation scatters onto their own lines.
    """
    toks = [w["text"] for w in words]
    nums = [t for t in toks if NUM.match(t)]
    if len(nums) < n_expected:
        return None
    nums = nums[-n_expected:]
    # everything before the first of those trailing numbers is the label
    cut = len(toks) - n_expected
    label = " ".join(toks[:cut])
    label = JUNK.sub("", label)

    jersey = JERSEY.search(label)
    pos = POS.search(label)
    name = JERSEY.split(label)[0]
    name = re.sub(r"\s+", " ", name).strip(" .,-")
    return {
        "name": name,
        "jersey": jersey.group(1) if jersey else "",
        "pos": pos.group(1) if pos else "",
        "nums": nums,
    }


# --------------------------------------------------------------------------
# notes lines (2B:, TB:, SB:, E:, P-S:, BF:, ...)
# --------------------------------------------------------------------------

NOTE_KEYS = ["2B", "3B", "HR", "TB", "SF", "SAC", "HBP", "SB", "CS", "LOB",
             "W", "L", "SV", "P-S", "WP", "BF", "E", "PB", "DP"]
NOTE_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in NOTE_KEYS) + r"):\s*")


def parse_notes(blob):
    blob = JUNK.sub("", re.sub(r"\s+", " ", blob)).strip()
    if not blob:
        return {}
    parts = NOTE_RE.split(blob)
    out, i = {}, 1
    while i + 1 < len(parts) + 1 and i < len(parts):
        key, val = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        out[key] = val.strip().strip(",")
        i += 2
    return out


PS_RE = re.compile(r"([A-Z][A-Za-z'\-]*(?:\s+[A-Z][A-Za-z'\-]*)*)\s+(\d+)-(\d+)")


def pitch_counts(ps_blob):
    """'A Dantry 85-49, A Glomb 55-26' -> {'A Dantry': (85, 49), ...}"""
    return {m.group(1).strip(): (int(m.group(2)), int(m.group(3)))
            for m in PS_RE.finditer(ps_blob or "")}


def same_player(a, b):
    """Match names across the ellipsis truncation GameChanger applies in tables.

    The table cell may read "L Bruck" while the notes line says "L Bruckner",
    so compare last names by prefix rather than equality.
    """
    # Teams write names both ways -- "S Chimino" and "Bella H" -- so the
    # surname is not reliably the last token. Compare the longest token,
    # which is the real name in either convention.
    key = lambda n: max(n.replace(".", " ").split(), key=len).lower()
    ka, kb = key(a), key(b)
    short, long_ = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    return len(short) >= 3 and long_.startswith(short)


def bf_counts(bf_blob):
    """'A Dantry 21, A Glomb 14' -> {'A Dantry': 21, ...}"""
    out = {}
    for chunk in (bf_blob or "").split(","):
        m = re.match(r"\s*([A-Za-z' \-]+?)\s+(\d+)\s*$", chunk)
        if m:
            out[m.group(1).strip()] = int(m.group(2))
    return out


# --------------------------------------------------------------------------
# main parse
# --------------------------------------------------------------------------

BAT_COLS = ["AB", "R", "H", "RBI", "BB", "SO"]
PIT_COLS = ["IP", "H", "R", "ER", "BB", "SO", "HR"]


def parse_linescore(page, y_bat, left_team, right_team):
    """The inning grid above BATTING.

    Row order follows the tables: first row is the team named first in the
    filename (the left-hand column), regardless of home/away.

    The team abbreviation sometimes sits a point or two above its own digits,
    so a fixed y-bucket splits the row in half. Instead of guessing a
    tolerance, read the header to learn how many innings the game went, then
    accumulate numbers until a full row's worth has arrived.
    """
    buckets = defaultdict(list)
    for w in page.extract_words():
        if w["top"] < y_bat:
            buckets[round(w["top"] / 3.0)].append(w)

    order = sorted(buckets)
    header_i, n_innings = None, 0
    for i, key in enumerate(order):
        toks = [w["text"] for w in sorted(buckets[key], key=lambda w: w["x0"])]
        if toks[-3:] == ["R", "H", "E"]:
            header_i, n_innings = i, sum(1 for t in toks if NUM.match(t))
            break
    if header_i is None or n_innings == 0:
        return []

    want = n_innings + 3
    rows, acc = [], []
    for key in order[header_i + 1:]:
        toks = [w["text"] for w in sorted(buckets[key], key=lambda w: w["x0"])]
        acc += [int(t) for t in toks if NUM.match(t)]
        while len(acc) >= want:
            rows.append(acc[:want])
            acc = acc[want:]
        if len(rows) == 2:
            break
    if len(rows) < 2:
        return []

    out = []
    for team, opp, vals in ((left_team, right_team, rows[0]),
                            (right_team, left_team, rows[1])):
        out.append({"team": team, "opponent": opp, "innings": vals[:-3],
                    "R": vals[-3], "H": vals[-2], "E": vals[-1]})
    return out


def find_marker(page, text):
    for w in page.extract_words():
        if w["text"] == text:
            return w["top"]
    return None


def parse_pdf(path):
    left_team, right_team, date = parse_filename(path)
    game_id = f"{date}_{left_team}_vs_{right_team}"

    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        mid_x = page.width / 2
        y_bat = find_marker(page, "BATTING")
        y_pit = find_marker(page, "PITCHING")
        if y_bat is None or y_pit is None:
            raise ValueError(f"{path}: could not locate BATTING/PITCHING markers")

        bat_L, bat_R = rows_by_column(page, y_bat + 1, y_pit, mid_x)
        pit_L, pit_R = rows_by_column(page, y_pit + 1, page.height, mid_x)
        line = parse_linescore(page, y_bat, left_team, right_team)
        venue = ""
        for w in page.extract_words():
            if w["text"] in ("Home", "Away") and w["top"] < y_bat:
                venue = w["text"]
                break

    batting, pitching, notes = [], [], {}

    for team, opp, rows, side in (
        (left_team, right_team, bat_L, "L"),
        (right_team, left_team, bat_R, "R"),
    ):
        note_blob, in_notes = [], False
        for words in rows:
            txt = row_text(words)
            # Note blocks wrap across several visual lines; the continuation
            # lines carry no "KEY:" of their own, so latch on and keep going.
            if NOTE_RE.search(txt):
                in_notes = True
            if in_notes:
                note_blob.append(txt)
                continue
            if txt.startswith(("Lady", "AB", "Totals")):
                continue
            rec = split_name_and_nums(words, len(BAT_COLS))
            if not rec:
                continue
            row = {"game_id": game_id, "date": date, "team": team,
                   "opponent": opp, "player": rec["name"],
                   "jersey": rec["jersey"], "pos": rec["pos"]}
            row.update(dict(zip(BAT_COLS, (int(float(n)) for n in rec["nums"]))))
            batting.append(row)
        notes[(team, "bat")] = parse_notes(" ".join(note_blob))

    for team, opp, rows in (
        (left_team, right_team, pit_L),
        (right_team, left_team, pit_R),
    ):
        note_blob, in_notes = [], False
        for words in rows:
            txt = row_text(words)
            if NOTE_RE.search(txt):
                in_notes = True
            if in_notes:
                if not txt.startswith("Scorekeeping"):
                    note_blob.append(txt)
                continue
            if txt.startswith(("Lady", "IP", "Totals", "Scorekeeping")):
                continue
            rec = split_name_and_nums(words, len(PIT_COLS))
            if not rec:
                continue
            row = {"game_id": game_id, "date": date, "team": team,
                   "opponent": opp, "player": rec["name"], "jersey": rec["jersey"]}
            vals = rec["nums"]
            row["IP"] = float(vals[0])
            row.update(dict(zip(PIT_COLS[1:], (int(float(n)) for n in vals[1:]))))
            pitching.append(row)
        notes[(team, "pit")] = parse_notes(" ".join(note_blob))

    # fold pitch counts / batters faced back onto the pitching rows
    for team in (left_team, right_team):
        n = notes.get((team, "pit"), {})
        ps, bf = pitch_counts(n.get("P-S")), bf_counts(n.get("BF"))
        for row in pitching:
            if row["team"] != team:
                continue
            for who, (p, s) in ps.items():
                if same_player(who, row["player"]):
                    row["pitches"], row["strikes"] = p, s
            for who, v in bf.items():
                if same_player(who, row["player"]):
                    row["BF"] = v
            row.setdefault("pitches", "")
            row.setdefault("strikes", "")
            row.setdefault("BF", "")
            row["decision"] = ""
            for tag in ("W", "L", "SV"):
                who = n.get(tag, "")
                if who and same_player(who, row["player"]):
                    row["decision"] = tag

    # per-game extras for batters: extra-base hits, steals, errors
    for team in (left_team, right_team):
        nb = notes.get((team, "bat"), {})
        npi = notes.get((team, "pit"), {})
        tally = defaultdict(lambda: defaultdict(int))
        for key in ("2B", "3B", "HR", "SB", "CS", "HBP", "SF"):
            for chunk in (nb.get(key) or "").split(","):
                m = re.match(r"\s*([A-Za-z' \-]+?)(?:\s+(\d+))?\s*$", chunk)
                if m and m.group(1).strip():
                    tally[m.group(1).strip()][key] += int(m.group(2) or 1)
        for chunk in (npi.get("E") or "").split(","):
            m = re.match(r"\s*([A-Za-z' \-]+?)(?:\s+(\d+))?\s*$", chunk)
            if m and m.group(1).strip():
                tally[m.group(1).strip()]["E"] += int(m.group(2) or 1)
        for row in batting:
            if row["team"] != team:
                continue
            for who, d in tally.items():
                if same_player(who, row["player"]):
                    for k, v in d.items():
                        row[k] = v
            for k in ("2B", "3B", "HR", "SB", "CS", "HBP", "SF", "E"):
                row.setdefault(k, 0)

    games = []
    for side in line:
        other = next(x for x in line if x["team"] != side["team"])
        games.append({
            "game_id": game_id, "date": date,
            "team": side["team"], "opponent": side["opponent"],
            # the Home/Away flag on the page describes the first-named team
            "site": (venue if side["team"] == left_team else
                     {"Home": "Away", "Away": "Home"}.get(venue, "")),
            "R": side["R"], "H": side["H"], "E": side["E"],
            "RA": other["R"], "HA": other["H"], "EA": other["E"],
            "result": "W" if side["R"] > other["R"] else "L" if side["R"] < other["R"] else "T",
            "innings": len(side["innings"]),
            "by_inning": "-".join(str(i) for i in side["innings"]),
        })
    return batting, pitching, games


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--outdir", default="data")
    args = ap.parse_args()

    import pandas as pd
    all_bat, all_pit, all_games = [], [], []
    for p in args.pdfs:
        b, t, g = parse_pdf(p)
        all_bat += b
        all_pit += t
        all_games += g
        print(f"{pathlib.Path(p).name}: {len(b)} batting rows, {len(t)} pitching rows",
              file=sys.stderr)

    out = pathlib.Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_bat).to_csv(out / "batting_by_game.csv", index=False)
    pd.DataFrame(all_pit).to_csv(out / "pitching_by_game.csv", index=False)
    pd.DataFrame(all_games).to_csv(out / "games.csv", index=False)
    print(f"wrote {out/'batting_by_game.csv'} and {out/'pitching_by_game.csv'}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
