#!/usr/bin/env python3
"""Export per-team gold income time series from SQLite dataset.

Adds 'goldIncome' field to each school's heatmap JSON file,
following the same format as 'ammo' data.
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rmuc_2026_region_dataset.sqlite')
HEATMAP_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'heatmap')

# 5-second intervals, 0-420s (84 points)
INTERVAL = 5
MAX_TIME = 420
NUM_POINTS = MAX_TIME // INTERVAL  # 84

QUERY = """
SELECT 学校名, 赛区, game_id, 局号, 时刻秒, 队伍总金币
FROM timeseries
WHERE 机器人类型='工程' AND 时刻秒 >= 0 AND 时刻秒 <= 420
ORDER BY 学校名, 赛区, game_id, 局号, 时刻秒;
"""


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(QUERY)

    # Group by school, zone, game
    # {school: {zone: {game_id: [(second, gold)]}}}
    school_data = {}
    for school, zone, game_id, _round, sec, gold in cur.fetchall():
        if gold is None:
            continue
        if school not in school_data:
            school_data[school] = {}
        if zone not in school_data[school]:
            school_data[school][zone] = {}
        if game_id not in school_data[school][zone]:
            school_data[school][zone][game_id] = []
        school_data[school][zone][game_id].append((sec, gold))

    conn.close()

    updated = 0
    created = 0

    for school, zones in school_data.items():
        for zone, games in zones.items():
            # Compute average gold at each time point across games
            # First, resample each game to fixed intervals
            game_curves = []
            for game_id, points in games.items():
                if len(points) < 10:
                    continue
                # Build interpolated curve at interval points
                curve = [0.0] * NUM_POINTS
                for sec, gold in points:
                    idx = min(int(sec // INTERVAL), NUM_POINTS - 1)
                    curve[idx] = gold  # last value in interval wins
                # Forward-fill
                for i in range(1, NUM_POINTS):
                    if curve[i] == 0 and curve[i-1] > 0:
                        curve[i] = curve[i-1]
                # Only use games that have data for most of the match
                if max(curve) > 0:
                    game_curves.append(curve)

            if not game_curves:
                continue

            # Average across games
            avg_curve = [0.0] * NUM_POINTS
            for i in range(NUM_POINTS):
                vals = [c[i] for c in game_curves if c[i] > 0]
                avg_curve[i] = round(sum(vals) / len(vals), 1) if vals else 0.0

            # Load existing heatmap JSON
            json_path = os.path.join(HEATMAP_DIR, zone, f'{school}.json')
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {}

            # Add goldIncome field
            if 'goldIncome' not in data:
                data['goldIncome'] = {}
            data['goldIncome']['工程'] = {
                'interval': INTERVAL,
                'data': avg_curve,
            }

            # Write back
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)

            if 'goldIncome' in data:
                updated += 1
            else:
                created += 1

    print(f'Done. Updated: {updated}, Created: {created}')
    print(f'Total schools: {len(school_data)}')


if __name__ == '__main__':
    main()
