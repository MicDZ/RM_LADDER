#!/usr/bin/env python3
"""
导出 RMUC 2026 比赛位置数据为 JSON 格式，用于生成场地热力图。
"""
import sqlite3
import json
import os
import base64
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rmuc_2026_region_dataset.sqlite')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'static')

# 热力图网格分辨率
GRID_SIZE = 60  # 60x60 网格

# 实际游戏区域坐标范围（根据数据分析）
GAME_X_MIN = 0
GAME_X_MAX = 28
GAME_Y_MIN = 0
GAME_Y_MAX = 15


def coord_to_grid(x, y, x_range, y_range):
    """将游戏坐标转换为网格索引"""
    grid_x = int((x - GAME_X_MIN) / x_range * (GRID_SIZE - 1))
    grid_y = int((y - GAME_Y_MIN) / y_range * (GRID_SIZE - 1))
    grid_x = max(0, min(GRID_SIZE - 1, grid_x))
    grid_y = max(0, min(GRID_SIZE - 1, grid_y))
    return grid_x, grid_y


def export_position_heatmap(conn):
    """导出各学校各兵种的位置热力图数据（按赛区），包含红蓝方分别统计"""
    cur = conn.cursor()

    x_range = GAME_X_MAX - GAME_X_MIN
    y_range = GAME_Y_MAX - GAME_Y_MIN

    print(f"游戏区域: X({GAME_X_MIN} ~ {GAME_X_MAX}), Y({GAME_Y_MIN} ~ {GAME_Y_MAX})")

    # 兵种类型
    robot_types = ['英雄', '工程', '步兵3', '步兵4', '空中', '哨兵']

    # 初始化数据结构
    heatmap_data = {}

    # 按赛区、学校和兵种统计位置分布
    print("统计各赛区各学校各兵种位置分布（分红蓝方）...")

    # 获取所有赛区
    cur.execute('SELECT DISTINCT 赛区 FROM timeseries ORDER BY 赛区')
    regions = [row[0] for row in cur.fetchall()]

    for region in regions:
        print(f"  处理 {region}...")
        heatmap_data[region] = {}

        for robot_type in robot_types:
            # 只统计游戏区域内的坐标，按阵营分开统计
            cur.execute('''
            SELECT 学校名, 阵营, x, y
            FROM timeseries
            WHERE 赛区 = ? AND 机器人类型 = ? AND x IS NOT NULL AND y IS NOT NULL
            AND x >= ? AND x <= ? AND y >= ? AND y <= ?
            ''', (region, robot_type, GAME_X_MIN, GAME_X_MAX, GAME_Y_MIN, GAME_Y_MAX))

            # 分红蓝方统计: {school: {'red': grid, 'blue': grid}}
            school_grids = defaultdict(lambda: {'red': [[0] * GRID_SIZE for _ in range(GRID_SIZE)],
                                                'blue': [[0] * GRID_SIZE for _ in range(GRID_SIZE)]})

            for row in cur.fetchall():
                school, faction, x, y = row
                faction_key = 'red' if faction == '红' else 'blue'
                grid_x, grid_y = coord_to_grid(x, y, x_range, y_range)
                school_grids[school][faction_key][grid_y][grid_x] += 1

            # 归一化并存储
            for school, grids in school_grids.items():
                if school not in heatmap_data[region]:
                    heatmap_data[region][school] = {}

                # 找到红蓝方的最大值分别归一化
                red_max = max(max(row) for row in grids['red'])
                blue_max = max(max(row) for row in grids['blue'])

                if red_max > 0:
                    normalized_red = [[round(v / red_max * 100) for v in row] for row in grids['red']]
                else:
                    normalized_red = grids['red']

                if blue_max > 0:
                    normalized_blue = [[round(v / blue_max * 100) for v in row] for row in grids['blue']]
                else:
                    normalized_blue = grids['blue']

                heatmap_data[region][school][robot_type] = {
                    'red': normalized_red,
                    'blue': normalized_blue
                }

        # 导出易伤热力图（雷达标记敌方）
        print(f"  处理 {region} 易伤数据...")

        # 预先加载该赛区所有易伤数据，按game_id和阵营组织
        cur.execute('''
        SELECT game_id, 阵营, x, y
        FROM timeseries
        WHERE 赛区 = ? AND 是否易伤 = 1
        AND x IS NOT NULL AND y IS NOT NULL
        AND x >= ? AND x <= ? AND y >= ? AND y <= ?
        ''', (region, GAME_X_MIN, GAME_X_MAX, GAME_Y_MIN, GAME_Y_MAX))

        # {game_id: {'红': [(x,y), ...], '蓝': [(x,y), ...]}}
        vulnerable_by_game = defaultdict(lambda: {'红': [], '蓝': []})
        for game_id, faction, x, y in cur.fetchall():
            vulnerable_by_game[game_id][faction].append((x, y))

        # 获取该赛区每个学校的参赛记录
        cur.execute('''
        SELECT DISTINCT 学校名, 阵营, game_id
        FROM timeseries
        WHERE 赛区 = ?
        ''', (region,))

        # {school: {game_id: faction}}
        school_games = defaultdict(dict)
        for school, faction, game_id in cur.fetchall():
            school_games[school][game_id] = faction

        # 为每个学校计算易伤热力图
        # 易伤含义：敌方机器人被我方雷达标记的位置
        for school, games in school_games.items():
            if school not in heatmap_data[region]:
                heatmap_data[region][school] = {}

            grid_red = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]  # 我方红时，敌方蓝被标记
            grid_blue = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]  # 我方蓝时，敌方红被标记

            for game_id, my_faction in games.items():
                # 查询敌方阵营机器人被标记易伤的位置
                enemy_faction = '蓝' if my_faction == '红' else '红'
                enemy_vulnerable = vulnerable_by_game.get(game_id, {}).get(enemy_faction, [])

                target_grid = grid_red if my_faction == '红' else grid_blue

                for x, y in enemy_vulnerable:
                    grid_x, grid_y = coord_to_grid(x, y, x_range, y_range)
                    target_grid[grid_y][grid_x] += 1

            red_max = max(max(row) for row in grid_red) if any(any(row) for row in grid_red) else 0
            blue_max = max(max(row) for row in grid_blue) if any(any(row) for row in grid_blue) else 0
            max_count = max(red_max, blue_max)

            if max_count > 0:
                normalized_red = [[round(v / max_count * 100) for v in row] for row in grid_red] if red_max > 0 else grid_red
                normalized_blue = [[round(v / max_count * 100) for v in row] for row in grid_blue] if blue_max > 0 else grid_blue
                heatmap_data[region][school]['易伤'] = {
                    'red': normalized_red,
                    'blue': normalized_blue
                }

    # Build region -> school list mapping
    regionSchools = {}
    for region in regions:
        regionSchools[region] = sorted(list(heatmap_data.get(region, {}).keys()))

    return {
        "config": {
            "gridSize": GRID_SIZE,
            "xRange": [GAME_X_MIN, GAME_X_MAX],
            "yRange": [GAME_Y_MIN, GAME_Y_MAX],
            "robotTypes": robot_types + ['易伤'],
            "regions": regions,
            "regionSchools": regionSchools
        },
        "data": heatmap_data
    }


def encode_grid(grid):
    """将60x60网格编码为base64字符串，每个值用1字节(0-100)"""
    flat = bytes([v for row in grid for v in row])
    return base64.b64encode(flat).decode('ascii')


def encode_robot_data(robot_data):
    """编码兵种数据，支持 {red: grid, blue: grid} 格式"""
    if isinstance(robot_data, dict) and 'red' in robot_data:
        return {
            'red': encode_grid(robot_data['red']),
            'blue': encode_grid(robot_data['blue'])
        }
    return encode_grid(robot_data)


def main():
    print(f"连接数据库: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)

    # 导出热力图数据
    print("\n=== 导出位置热力图数据 ===")
    heatmap_data = export_position_heatmap(conn)

    # 打散为按学校分文件的结构（base64编码）
    heatmap_dir = os.path.join(OUTPUT_DIR, 'heatmap')
    os.makedirs(heatmap_dir, exist_ok=True)

    # 保存 config.json
    config_path = os.path.join(heatmap_dir, 'config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(heatmap_data['config'], f, ensure_ascii=False)
    print(f"已保存: {config_path}")

    # 按赛区/学校保存（base64编码）
    total_files = 0
    for region, schools in heatmap_data['data'].items():
        region_dir = os.path.join(heatmap_dir, region)
        os.makedirs(region_dir, exist_ok=True)
        for school, robots in schools.items():
            encoded = {rtype: encode_robot_data(data) for rtype, data in robots.items()}
            school_path = os.path.join(region_dir, f'{school}.json')
            with open(school_path, 'w', encoding='utf-8') as f:
                json.dump(encoded, f, ensure_ascii=False, separators=(',', ':'))
            total_files += 1
    print(f"已保存 {total_files} 个学校文件到 {heatmap_dir}/")

    conn.close()
    print("\n导出完成!")


if __name__ == '__main__':
    main()
