#!/usr/bin/env python3
"""Export per-team assembly stats from SQLite dataset to JSON."""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rmuc_2026_region_dataset.sqlite')
OUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'assembly_stats_2026.json')

QUERY = """
SELECT 学校名, 赛区,
       COUNT(*) as total,
       SUM(CASE WHEN 类别='等级1' THEN 1 ELSE 0 END) as level1,
       ROUND(AVG(CASE WHEN 类别='等级1' THEN 数值 END), 2) as avg1,
       ROUND(MIN(CASE WHEN 类别='等级1' THEN 数值 END), 2) as min1,
       SUM(CASE WHEN 类别='等级2' THEN 1 ELSE 0 END) as level2,
       ROUND(AVG(CASE WHEN 类别='等级2' THEN 数值 END), 2) as avg2,
       ROUND(MIN(CASE WHEN 类别='等级2' THEN 数值 END), 2) as min2,
       SUM(CASE WHEN 类别='等级3' THEN 1 ELSE 0 END) as level3,
       ROUND(AVG(CASE WHEN 类别='等级3' THEN 数值 END), 2) as avg3,
       ROUND(MIN(CASE WHEN 类别='等级3' THEN 数值 END), 2) as min3,
       ROUND(MIN(数值), 2) as min_all,
       SUM(CASE WHEN 备注 IS NOT NULL AND 备注 != '' THEN 1 ELSE 0 END) as penalties
FROM events
WHERE 事件类型 = '装配成功'
GROUP BY 学校名, 赛区
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
            'total': row[2],
            'level1': row[3], 'avg1': row[4], 'min1': row[5],
            'level2': row[6], 'avg2': row[7], 'min2': row[8],
            'level3': row[9], 'avg3': row[10], 'min3': row[11],
            'minAll': row[12],
            'penalties': row[13],
        }

    conn.close()

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'Wrote {OUT_PATH}')
    total_teams = sum(len(v) for v in result.values())
    print(f'Zones: {len(result)}, Teams: {total_teams}')

if __name__ == '__main__':
    main()
