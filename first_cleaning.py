#!/usr/bin/env python3
"""First-pass cleaning for NHL team and 2025 enhancement data."""
# run with python3 -m py_compile first_cleaning.py

from __future__ import annotations

import csv
from datetime import datetime, date
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "hockey_data"
OUTPUT_DIR = DATA_DIR / "cleaned"


def parse_game_date(raw_value: str) -> date:
    return datetime.strptime(raw_value, "%Y%m%d").date()


def normalize_home_away(raw_value: str) -> str:
    value = (raw_value or "").strip().upper()
    if value == "HOME":
        return "home"
    if value == "AWAY":
        return "away"
    return value.lower()


def to_float(raw_value: str) -> float | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    return float(value)


def format_number(value: float | None, decimals: int = 4) -> str:
    if value is None:
        return ""
    rounded = round(value, decimals)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")


def write_csv(output_path: Path, rows: Iterable[dict], fieldnames: list[str]) -> int:
    row_count = 0
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
            row_count += 1
    return row_count


def add_rest_day_fields(rows: list[dict]) -> None:
    last_game_date_by_team: dict[str, date] = {}

    for row in sorted(rows, key=lambda item: (item["team"], item["_date_obj"], item["game_id"])):
        previous_date = last_game_date_by_team.get(row["team"])
        if previous_date is None:
            row["rest_days"] = ""
            row["is_back_to_back"] = "0"
        else:
            rest_days = max((row["_date_obj"] - previous_date).days - 1, 0)
            row["rest_days"] = str(rest_days)
            row["is_back_to_back"] = "1" if rest_days == 0 else "0"
        last_game_date_by_team[row["team"]] = row["_date_obj"]


def build_team_table() -> list[dict]:
    source_path = DATA_DIR / "all_teams.csv"
    rows: list[dict] = []

    with source_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            if raw.get("position") != "Team Level" or raw.get("situation") != "all":
                continue

            game_date = parse_game_date(raw["gameDate"])
            goals_for = to_float(raw.get("goalsFor")) or 0.0
            goals_against = to_float(raw.get("goalsAgainst")) or 0.0

            row = {
                "game_id": raw["gameId"],
                "date": game_date.isoformat(),
                "season": raw["season"],
                "team": raw["playerTeam"],
                "opponent": raw["opposingTeam"],
                "home_or_away": normalize_home_away(raw["home_or_away"]),
                "goals_for": format_number(goals_for),
                "goals_against": format_number(goals_against),
                "shots_for": format_number(to_float(raw.get("shotsOnGoalFor"))),
                "shots_against": format_number(to_float(raw.get("shotsOnGoalAgainst"))),
                "xg_for": format_number(to_float(raw.get("xGoalsFor"))),
                "xg_against": format_number(to_float(raw.get("xGoalsAgainst"))),
                "high_danger_chances_for": format_number(to_float(raw.get("highDangerShotsFor"))),
                "high_danger_chances_against": format_number(to_float(raw.get("highDangerShotsAgainst"))),
                "corsi_for_pct": format_number(to_float(raw.get("corsiPercentage"))),
                "fenwick_for_pct": format_number(to_float(raw.get("fenwickPercentage"))),
                "result": "W" if goals_for > goals_against else "L" if goals_for < goals_against else "T",
                "rest_days": "",
                "is_back_to_back": "",
                "_date_obj": game_date,
            }
            rows.append(row)

    add_rest_day_fields(rows)

    for row in rows:
        row.pop("_date_obj", None)

    return sorted(rows, key=lambda item: (item["date"], item["game_id"], item["team"]))


def build_goalie_table() -> list[dict]:
    source_path = DATA_DIR / "2025_goalies.csv"
    rows: list[dict] = []
    starters: dict[tuple[str, str], dict] = {}

    with source_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            if raw.get("season") != "2025" or raw.get("situation") != "all" or raw.get("position") != "G":
                continue

            game_date = parse_game_date(raw["gameDate"])
            shots_against = to_float(raw.get("ongoal"))
            goals_against = to_float(raw.get("goals")) or 0.0
            save_percentage = None
            if shots_against is not None and shots_against > 0:
                save_percentage = (shots_against - goals_against) / shots_against

            row = {
                "game_id": raw["gameId"],
                "date": game_date.isoformat(),
                "season": raw["season"],
                "team": raw["playerTeam"],
                "opponent": raw["opposingTeam"],
                "home_or_away": normalize_home_away(raw["home_or_away"]),
                "goalie_id": raw["playerId"],
                "goalie_name": raw["name"],
                "goalie_icetime": format_number(to_float(raw.get("icetime"))),
                "shots_against": format_number(shots_against),
                "goals_against": format_number(goals_against),
                "xg_against": format_number(to_float(raw.get("xGoals"))),
                "save_percentage": format_number(save_percentage),
                "starting_goalie_flag": "0",
            }
            rows.append(row)

            starter_key = (row["game_id"], row["team"])
            current_best = starters.get(starter_key)
            current_icetime = to_float(raw.get("icetime")) or 0.0
            current_shots = shots_against or 0.0
            if current_best is None:
                starters[starter_key] = {
                    "goalie_id": row["goalie_id"],
                    "icetime": current_icetime,
                    "shots_against": current_shots,
                }
                continue

            if (current_icetime, current_shots) > (current_best["icetime"], current_best["shots_against"]):
                starters[starter_key] = {
                    "goalie_id": row["goalie_id"],
                    "icetime": current_icetime,
                    "shots_against": current_shots,
                }

    for row in rows:
        starter = starters.get((row["game_id"], row["team"]))
        if starter and starter["goalie_id"] == row["goalie_id"]:
            row["starting_goalie_flag"] = "1"

    return sorted(rows, key=lambda item: (item["date"], item["game_id"], item["team"], item["goalie_name"]))


def build_skater_table() -> list[dict]:
    source_path = DATA_DIR / "2025_skaters.csv"
    rows: list[dict] = []

    with source_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            if raw.get("season") != "2025" or raw.get("situation") != "all":
                continue

            game_date = parse_game_date(raw["gameDate"])
            row = {
                "game_id": raw["gameId"],
                "date": game_date.isoformat(),
                "season": raw["season"],
                "team": raw["playerTeam"],
                "opponent": raw["opposingTeam"],
                "home_or_away": normalize_home_away(raw["home_or_away"]),
                "skater_id": raw["playerId"],
                "skater_name": raw["name"],
                "position": raw["position"],
                "skater_icetime": format_number(to_float(raw.get("icetime"))),
                "skater_shifts": format_number(to_float(raw.get("shifts"))),
                "skater_game_score": format_number(to_float(raw.get("gameScore"))),
                "onice_xg_pct": format_number(to_float(raw.get("onIce_xGoalsPercentage"))),
                "onice_corsi_pct": format_number(to_float(raw.get("onIce_corsiPercentage"))),
                "onice_fenwick_pct": format_number(to_float(raw.get("onIce_fenwickPercentage"))),
                "skater_goals": format_number(to_float(raw.get("I_F_goals"))),
                "skater_points": format_number(to_float(raw.get("I_F_points"))),
                "skater_shots_on_goal": format_number(to_float(raw.get("I_F_shotsOnGoal"))),
                "skater_takeaways": format_number(to_float(raw.get("I_F_takeaways"))),
                "skater_giveaways": format_number(to_float(raw.get("I_F_giveaways"))),
            }
            rows.append(row)

    return sorted(rows, key=lambda item: (item["date"], item["game_id"], item["team"], item["skater_name"]))


def build_line_table() -> list[dict]:
    source_path = DATA_DIR / "2025_lines.csv"
    rows: list[dict] = []

    with source_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            if raw.get("season") != "2025" or raw.get("situation") != "5on5":
                continue

            game_date = parse_game_date(raw["gameDate"])
            row = {
                "game_id": raw["gameId"],
                "date": game_date.isoformat(),
                "season": raw["season"],
                "team": raw["playerTeam"],
                "opponent": raw["opposingTeam"],
                "home_or_away": normalize_home_away(raw["home_or_away"]),
                "line_id": raw["lineId"],
                "line_name": raw["name"],
                "situation": raw["situation"],
                "line_icetime": format_number(to_float(raw.get("icetime"))),
                "line_xg_pct": format_number(to_float(raw.get("xGoalsPercentage"))),
                "corsi_for_pct": format_number(to_float(raw.get("corsiPercentage"))),
                "fenwick_for_pct": format_number(to_float(raw.get("fenwickPercentage"))),
                "xg_for": format_number(to_float(raw.get("xGoalsFor"))),
                "xg_against": format_number(to_float(raw.get("xGoalsAgainst"))),
                "goals_for": format_number(to_float(raw.get("goalsFor"))),
                "goals_against": format_number(to_float(raw.get("goalsAgainst"))),
                "shots_for": format_number(to_float(raw.get("shotsOnGoalFor"))),
                "shots_against": format_number(to_float(raw.get("shotsOnGoalAgainst"))),
            }
            rows.append(row)

    return sorted(rows, key=lambda item: (item["date"], item["game_id"], item["team"], item["line_name"]))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    team_rows = build_team_table()
    goalie_rows = build_goalie_table()
    skater_rows = build_skater_table()
    line_rows = build_line_table()

    outputs = {
        "games_team_clean.csv": (
            team_rows,
            [
                "game_id",
                "date",
                "season",
                "team",
                "opponent",
                "home_or_away",
                "goals_for",
                "goals_against",
                "shots_for",
                "shots_against",
                "xg_for",
                "xg_against",
                "high_danger_chances_for",
                "high_danger_chances_against",
                "corsi_for_pct",
                "fenwick_for_pct",
                "result",
                "rest_days",
                "is_back_to_back",
            ],
        ),
        "games_goalie_2025_clean.csv": (
            goalie_rows,
            [
                "game_id",
                "date",
                "season",
                "team",
                "opponent",
                "home_or_away",
                "goalie_id",
                "goalie_name",
                "goalie_icetime",
                "shots_against",
                "goals_against",
                "xg_against",
                "save_percentage",
                "starting_goalie_flag",
            ],
        ),
        "games_skater_2025_clean.csv": (
            skater_rows,
            [
                "game_id",
                "date",
                "season",
                "team",
                "opponent",
                "home_or_away",
                "skater_id",
                "skater_name",
                "position",
                "skater_icetime",
                "skater_shifts",
                "skater_game_score",
                "onice_xg_pct",
                "onice_corsi_pct",
                "onice_fenwick_pct",
                "skater_goals",
                "skater_points",
                "skater_shots_on_goal",
                "skater_takeaways",
                "skater_giveaways",
            ],
        ),
        "games_line_2025_clean.csv": (
            line_rows,
            [
                "game_id",
                "date",
                "season",
                "team",
                "opponent",
                "home_or_away",
                "line_id",
                "line_name",
                "situation",
                "line_icetime",
                "line_xg_pct",
                "corsi_for_pct",
                "fenwick_for_pct",
                "xg_for",
                "xg_against",
                "goals_for",
                "goals_against",
                "shots_for",
                "shots_against",
            ],
        ),
    }

    for filename, (rows, fieldnames) in outputs.items():
        row_count = write_csv(OUTPUT_DIR / filename, rows, fieldnames)
        print(f"Wrote {row_count} rows to {OUTPUT_DIR / filename}")


if __name__ == "__main__":
    main()
