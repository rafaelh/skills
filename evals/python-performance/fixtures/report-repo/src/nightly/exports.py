"""CSV side-exports of the digest data, for the weekly spreadsheet."""

from __future__ import annotations


def group_by_team(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["team"], []).append(row)
    return grouped


def as_csv(rows, columns):
    lines = [",".join(columns)]
    for i in range(len(rows)):
        lines.append(",".join(str(rows[i][column]) for column in columns))
    return "\n".join(lines) + "\n"


def team_is_known(index, team):
    return team in index.keys()
