#!/usr/bin/env python3
"""Export per-team dart (飞镖) stats from SQLite dataset to JSON."""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rmuc_2026_region_dataset.sqlite')
OUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'dart_stats_2026.json')

QUERY = """
SELECT 学校名, 赛区,
       COUNT(CASE WHEN 事件类型='飞镖闸门开' THEN 1 END) as gate_open,
       COUNT(CASE WHEN 事件类型='飞镖命中' THEN 1 END) as total_hits,
       ROUND(SUM(CASE WHEN 事件类型='飞镖命中' THEN 数值 ELSE 0 END), 1) as total_damage,
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='基地' THEN 1 ELSE 0 END) as base_hits,
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='前哨站' THEN 1 ELSE 0 END) as outpost_hits,
       ROUND(SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='基地' THEN 数值 ELSE 0 END), 1) as base_damage,
       ROUND(SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='前哨站' THEN 数值 ELSE 0 END), 1) as outpost_damage,
       -- Per-value breakdown for base hits
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='基地' AND 数值=200 THEN 1 ELSE 0 END) as base_200,
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='基地' AND 数值=300 THEN 1 ELSE 0 END) as base_300,
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='基地' AND 数值=625 THEN 1 ELSE 0 END) as base_625,
       -- Per-value breakdown for outpost hits
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='前哨站' AND 数值=330 THEN 1 ELSE 0 END) as outpost_330,
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='前哨站' AND 数值=530 THEN 1 ELSE 0 END) as outpost_530,
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='前哨站' AND 数值=670 THEN 1 ELSE 0 END) as outpost_670,
       SUM(CASE WHEN 事件类型='飞镖命中' AND 目标类型='前哨站' AND 数值=750 THEN 1 ELSE 0 END) as outpost_750
FROM events
WHERE 事件类型 IN ('飞镖闸门开','飞镖命中')
GROUP BY 学校名, 赛区
HAVING gate_open > 0 OR total_hits > 0
ORDER BY 赛区, 学校名;
"""


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(QUERY)

    result = {}
    for row in cur.fetchall():
        school, zone = row[0], row[1]
        if zone not in result:
            result[zone] = {}
        result[zone][school] = {
            'gateOpen': row[2],
            'totalHits': row[3],
            'totalDamage': row[4],
            'baseHits': row[5],
            'outpostHits': row[6],
            'baseDamage': row[7],
            'outpostDamage': row[8],
            'base200': row[9],
            'base300': row[10],
            'base625': row[11],
            'outpost330': row[12],
            'outpost530': row[13],
            'outpost670': row[14],
            'outpost750': row[15],
        }

    conn.close()

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'Wrote {OUT_PATH}')
    total_teams = sum(len(v) for v in result.values())
    print(f'Zones: {len(result)}, Teams: {total_teams}')


if __name__ == '__main__':
    main()
