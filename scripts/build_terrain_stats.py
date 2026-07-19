#!/usr/bin/env python3
"""Export per-team terrain traversal stats from SQLite dataset to JSON.

Tracks 飞坡 / 过中央高地 / 台阶跨越 for Hero, Infantry, Guard.
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rmuc_2026_region_dataset.sqlite')
OUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'terrain_stats_2026.json')

QUERY = """
WITH game_counts AS (
    SELECT 学校名, 赛区, COUNT(DISTINCT game_id) as games
    FROM timeseries
    WHERE 机器人类型 IN ('英雄', '步兵3', '步兵4', '哨兵')
    GROUP BY 学校名, 赛区
),
terrain AS (
    SELECT 学校名, 赛区,
           CASE WHEN 机器人类型 IN ('步兵3', '步兵4') THEN 'Infantry'
                WHEN 机器人类型 = '英雄' THEN 'Hero'
                WHEN 机器人类型 = '哨兵' THEN 'Guard' END as type,
           类别, COUNT(*) as cnt
    FROM events
    WHERE 事件类型='增益' AND 类别 IN ('飞坡', '过中央高地', '台阶跨越')
      AND 机器人类型 IN ('英雄', '步兵3', '步兵4', '哨兵')
    GROUP BY 学校名, 赛区, type, 类别
)
SELECT t.学校名, t.赛区, t.type, t.类别, t.cnt, g.games
FROM terrain t
JOIN game_counts g ON t.学校名 = g.学校名 AND t.赛区 = g.赛区
ORDER BY t.赛区, t.学校名, t.type, t.类别;
"""

TERRAIN_TYPES = ['飞坡', '过中央高地', '台阶跨越']


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(QUERY)

    # Structure: {zone: {school: {type: {terrain: {count, avg}}}}}
    result = {}
    for school, zone, rtype, terrain, cnt, games in cur.fetchall():
        if zone not in result:
            result[zone] = {}
        if school not in result[zone]:
            result[zone][school] = {}
        if rtype not in result[zone][school]:
            result[zone][school][rtype] = {'games': games}
        result[zone][school][rtype][terrain] = {
            'count': cnt,
            'avg': round(cnt / games, 2) if games > 0 else 0,
        }

    conn.close()

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'Wrote {OUT_PATH}')
    total_teams = sum(len(v) for v in result.values())
    print(f'Zones: {len(result)}, Teams: {total_teams}')


if __name__ == '__main__':
    main()
