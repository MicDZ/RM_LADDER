#!/usr/bin/env python3
"""Export per-team radar counter-UAV stats from SQLite dataset to JSON.

Generates:
- counter count per school per zone
- timing distribution (histogram buckets) for the distribution chart
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rmuc_2026_region_dataset.sqlite')
OUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'radar_stats_2026.json')

QUERY = """
SELECT radar_school as school, 赛区 as zone,
       COUNT(*) as counter_cnt,
       GROUP_CONCAT(ROUND(时刻秒, 0)) as times
FROM (
    SELECT e.时刻秒, e.赛区,
           CASE WHEN e.阵营='蓝' THEN m.红方学校 ELSE m.蓝方学校 END as radar_school
    FROM events e
    JOIN matches m ON e.game_id = m.game_id AND e.局号 = m.局号
    WHERE e.事件类型='雷达反制UAV'
)
GROUP BY radar_school, 赛区
ORDER BY 赛区, counter_cnt DESC;
"""

# Histogram bucket boundaries (seconds)
# Match is ~420s (7min), split into 30s buckets
BUCKET_SIZE = 30
BUCKET_EDGES = list(range(0, 421, BUCKET_SIZE))  # 0-30, 30-60, ..., 390-420


def make_histogram(times_str):
    """Convert comma-separated times to histogram buckets."""
    if not times_str:
        return [0] * len(BUCKET_EDGES)
    times = [float(t) for t in times_str.split(',')]
    buckets = [0] * len(BUCKET_EDGES)
    for t in times:
        for i, edge in enumerate(BUCKET_EDGES):
            if i == len(BUCKET_EDGES) - 1:
                buckets[i] += 1
                break
            if t < BUCKET_EDGES[i + 1]:
                buckets[i] += 1
                break
    return buckets


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(QUERY)

    result = {}
    for school, zone, cnt, times_str in cur.fetchall():
        if zone not in result:
            result[zone] = {}
        buckets = make_histogram(times_str)
        result[zone][school] = {
            'counterCnt': cnt,
            'histogram': buckets,
        }

    conn.close()

    # Write JSON with histogram metadata
    output = {
        'bucketSize': BUCKET_SIZE,
        'bucketEdges': BUCKET_EDGES,
        'data': result,
    }

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'Wrote {OUT_PATH}')
    total_teams = sum(len(v) for v in result.values())
    print(f'Zones: {len(result)}, Teams: {total_teams}')


if __name__ == '__main__':
    main()
