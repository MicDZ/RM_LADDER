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
    """将60x60网格编码为稀疏格式字符串，只存储非零值
    格式: "idx:val,idx:val,..." (idx为扁平化索引, val为0-100的值)
    如果非零值超过30%，则回退到base64格式
    """
    flat = [v for row in grid for v in row]
    non_zero = [(i, v) for i, v in enumerate(flat) if v > 0]

    # 如果稀疏度不够，使用base64
    if len(non_zero) > len(flat) * 0.3:
        return base64.b64encode(bytes(flat)).decode('ascii')

    # 稀疏格式: "idx:val,idx:val,..."，全零时返回空字符串
    return ','.join(f'{i}:{v}' for i, v in non_zero) if non_zero else ''


def encode_robot_data(robot_data):
    """编码兵种数据，支持 {red: grid, blue: grid} 格式"""
    if isinstance(robot_data, dict) and 'red' in robot_data:
        return {
            'red': encode_grid(robot_data['red']),
            'blue': encode_grid(robot_data['blue'])
        }
    return encode_grid(robot_data)


def export_ammo_timeseries(conn):
    """导出各学校各兵种的平均累计发弹量时序数据"""
    cur = conn.cursor()

    # 英雄用42mm，步兵3/步兵4/空中/哨兵用17mm
    ammo_config = {
        '英雄': '累计42mm发弹',
        '步兵3': '累计17mm发弹',
        '步兵4': '累计17mm发弹',
        '无人机': '累计17mm发弹',
        '哨兵': '累计17mm发弹',
    }

    print("统计各学校各兵种平均累计发弹量...")

    # 获取所有赛区
    cur.execute('SELECT DISTINCT 赛区 FROM timeseries ORDER BY 赛区')
    regions = [row[0] for row in cur.fetchall()]

    result = {}

    for region in regions:
        print(f"  处理 {region}...")
        result[region] = {}

        for robot_type, ammo_field in ammo_config.items():
            # 查询该赛区该兵种的时序数据
            cur.execute(f'''
            SELECT 学校名, game_id, 时刻秒, [{ammo_field}]
            FROM timeseries
            WHERE 赛区 = ? AND 机器人类型 = ? AND [{ammo_field}] IS NOT NULL
            ORDER BY 学校名, game_id, 时刻秒
            ''', (region, robot_type))

            # 按学校和游戏组织数据
            # {school: {game_id: [(time, ammo), ...]}}
            school_games = defaultdict(lambda: defaultdict(list))
            for school, game_id, time_sec, ammo in cur.fetchall():
                school_games[school][game_id].append((time_sec, ammo))

            # 计算每个学校的平均曲线
            for school, games in school_games.items():
                if school not in result[region]:
                    result[region][school] = {}

                # 对每个游戏，取每个时间点的最大累计值（因为是累计值，取最后的值）
                # 然后对所有游戏取平均
                # 先确定时间点（取所有游戏的并集，按固定间隔采样）
                max_time = 0
                for game_data in games.values():
                    if game_data:
                        max_time = max(max_time, max(t for t, _ in game_data))

                if max_time == 0:
                    continue

                # 按5秒间隔采样
                sample_interval = 5
                time_points = list(range(0, int(max_time) + 1, sample_interval))

                # 对每个游戏，插值获取每个时间点的累计值
                game_curves = []
                for game_data in games.values():
                    if not game_data:
                        continue
                    # 按时间排序
                    game_data.sort(key=lambda x: x[0])
                    curve = []
                    for t in time_points:
                        # 找到 <= t 的最大时间点的值
                        val = 0
                        for gt, ga in game_data:
                            if gt <= t:
                                val = ga
                            else:
                                break
                        curve.append(val)
                    game_curves.append(curve)

                if not game_curves:
                    continue

                # 计算平均曲线
                avg_curve = []
                for i in range(len(time_points)):
                    vals = [gc[i] for gc in game_curves if i < len(gc)]
                    avg_curve.append(round(sum(vals) / len(vals), 1) if vals else 0)

                # 映射兵种名：步兵3/步兵4合并为步兵
                display_name = robot_type
                if robot_type in ('步兵3', '步兵4'):
                    display_name = '步兵'

                # 如果已有该兵种数据（如步兵3和步兵4），取平均
                if display_name in result[region][school]:
                    existing = result[region][school][display_name]
                    # 对齐长度
                    max_len = max(len(existing['data']), len(avg_curve))
                    merged = []
                    for i in range(max_len):
                        v1 = existing['data'][i] if i < len(existing['data']) else 0
                        v2 = avg_curve[i] if i < len(avg_curve) else 0
                        merged.append(round((v1 + v2) / 2, 1))
                    result[region][school][display_name] = {
                        'interval': sample_interval,
                        'data': merged
                    }
                else:
                    result[region][school][display_name] = {
                        'interval': sample_interval,
                        'data': avg_curve
                    }

    return result


def export_event_heatmap(conn):
    """导出各学校各兵种发弹（进攻）和受击热力图数据，按赛区/学校/兵种/阵营分别统计"""
    cur = conn.cursor()

    x_range = GAME_X_MAX - GAME_X_MIN
    y_range = GAME_Y_MAX - GAME_Y_MIN

    # 需要统计的兵种（跳过基地、前哨站）
    event_robot_types = ['英雄', '工程', '步兵3', '步兵4', '空中', '哨兵']
    # 步兵3/步兵4 合并为步兵
    merge_map = {'步兵3': '步兵', '步兵4': '步兵'}

    # 查询发弹事件位置（发弹方 = 进攻方）
    print("统计发弹（进攻）事件位置（按兵种）...")
    cur.execute('''
    SELECT DISTINCT e.学校名, e.阵营, e.机器人类型, t.x, t.y
    FROM events e
    JOIN timeseries t ON e.game_id = t.game_id AND e.robot_id = t.robot_id AND e.时刻秒 = t.时刻秒
    WHERE e.事件类型 = '发弹'
    AND e.机器人类型 IN ({})
    AND t.x IS NOT NULL AND t.y IS NOT NULL
    AND t.x >= ? AND t.x <= ? AND t.y >= ? AND t.y <= ?
    '''.format(','.join('?' * len(event_robot_types))),
    (*event_robot_types, GAME_X_MIN, GAME_X_MAX, GAME_Y_MIN, GAME_Y_MAX))

    # {school: {robot_type: {'red': grid, 'blue': grid}}}
    attack_grids = defaultdict(lambda: defaultdict(
        lambda: {'red': [[0] * GRID_SIZE for _ in range(GRID_SIZE)],
                 'blue': [[0] * GRID_SIZE for _ in range(GRID_SIZE)]}))
    for school, faction, robot_type, x, y in cur.fetchall():
        display_type = merge_map.get(robot_type, robot_type)
        faction_key = 'red' if faction == '红' else 'blue'
        grid_x, grid_y = coord_to_grid(x, y, x_range, y_range)
        attack_grids[school][display_type][faction_key][grid_y][grid_x] += 1

    # 查询受击事件位置（受击方 = 被攻击方）
    print("统计受击事件位置（按兵种）...")
    cur.execute('''
    SELECT DISTINCT e.学校名, e.阵营, e.机器人类型, t.x, t.y
    FROM events e
    JOIN timeseries t ON e.game_id = t.game_id AND e.robot_id = t.robot_id AND e.时刻秒 = t.时刻秒
    WHERE e.事件类型 = '受击'
    AND e.机器人类型 IN ({})
    AND t.x IS NOT NULL AND t.y IS NOT NULL
    AND t.x >= ? AND t.x <= ? AND t.y >= ? AND t.y <= ?
    '''.format(','.join('?' * len(event_robot_types))),
    (*event_robot_types, GAME_X_MIN, GAME_X_MAX, GAME_Y_MIN, GAME_Y_MAX))

    damage_grids = defaultdict(lambda: defaultdict(
        lambda: {'red': [[0] * GRID_SIZE for _ in range(GRID_SIZE)],
                 'blue': [[0] * GRID_SIZE for _ in range(GRID_SIZE)]}))
    for school, faction, robot_type, x, y in cur.fetchall():
        display_type = merge_map.get(robot_type, robot_type)
        faction_key = 'red' if faction == '红' else 'blue'
        grid_x, grid_y = coord_to_grid(x, y, x_range, y_range)
        damage_grids[school][display_type][faction_key][grid_y][grid_x] += 1

    # 获取所有赛区（从 timeseries 表）
    cur.execute('SELECT DISTINCT 学校名, 赛区 FROM timeseries')
    school_region_map = {school: region for school, region in cur.fetchall()}

    # 归一化并按赛区组织
    # result: {region: {school: {'attack': {type: {red, blue}}, 'damage': {type: {red, blue}}}}}
    result = {}
    for grids, label in [(attack_grids, 'attack'), (damage_grids, 'damage')]:
        for school, type_grids in grids.items():
            region = school_region_map.get(school)
            if not region:
                continue
            if region not in result:
                result[region] = {}
            if school not in result[region]:
                result[region][school] = {}
            result[region][school][label] = {}

            for robot_type, sides in type_grids.items():
                encoded = {}
                for faction_key in ('red', 'blue'):
                    grid = sides[faction_key]
                    max_val = max(max(row) for row in grid)
                    if max_val > 0:
                        normalized = [[round(v / max_val * 100) for v in row] for row in grid]
                    else:
                        normalized = grid
                    encoded[faction_key] = normalized
                result[region][school][label][robot_type] = encoded

    return result


def main():
    print(f"连接数据库: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)

    # 导出热力图数据
    print("\n=== 导出位置热力图数据 ===")
    heatmap_data = export_position_heatmap(conn)

    # 导出发弹量时序数据
    print("\n=== 导出发弹量时序数据 ===")
    ammo_data = export_ammo_timeseries(conn)

    # 导出发弹/受击热力图数据
    print("\n=== 导出发弹/受击热力图数据 ===")
    event_heatmap_data = export_event_heatmap(conn)

    # 打散为按学校分文件的结构（base64编码）
    heatmap_dir = os.path.join(OUTPUT_DIR, 'heatmap')
    os.makedirs(heatmap_dir, exist_ok=True)

    # 保存 config.json（添加 heatmapTypes 字段）
    config = heatmap_data['config']
    config['heatmapTypes'] = ['position', 'attack', 'damage']
    config_path = os.path.join(heatmap_dir, 'config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False)
    print(f"已保存: {config_path}")

    # 按赛区/学校保存（base64编码 + 发弹量数据）
    total_files = 0
    for region, schools in heatmap_data['data'].items():
        region_dir = os.path.join(heatmap_dir, region)
        os.makedirs(region_dir, exist_ok=True)
        for school, robots in schools.items():
            encoded = {rtype: encode_robot_data(data) for rtype, data in robots.items()}
            # 添加发弹量时序数据
            school_ammo = ammo_data.get(region, {}).get(school, {})
            if school_ammo:
                encoded['ammo'] = school_ammo
            school_path = os.path.join(region_dir, f'{school}.json')
            with open(school_path, 'w', encoding='utf-8') as f:
                json.dump(encoded, f, ensure_ascii=False, separators=(',', ':'))
            total_files += 1
    print(f"已保存 {total_files} 个学校位置热力图文件")

    # 保存发弹/受击热力图数据（按兵种分文件）
    event_files = 0
    for region, schools in event_heatmap_data.items():
        region_dir = os.path.join(heatmap_dir, region)
        os.makedirs(region_dir, exist_ok=True)
        for school, types in schools.items():
            for heatmap_type, robot_types_data in types.items():
                suffix = '_attack' if heatmap_type == 'attack' else '_damage'
                for robot_type, sides in robot_types_data.items():
                    encoded = encode_robot_data(sides)
                    file_path = os.path.join(region_dir, f'{school}{suffix}_{robot_type}.json')
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(encoded, f, ensure_ascii=False, separators=(',', ':'))
                    event_files += 1
    print(f"已保存 {event_files} 个进攻/受击热力图文件")

    # ── 生成全部学校聚合数据 ──
    print("\n=== 生成全部学校聚合数据 ===")
    agg_files = 0

    def sum_grids(grids_list):
        """求和多个 60x60 网格"""
        result = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]
        for grid in grids_list:
            for y in range(GRID_SIZE):
                for x in range(GRID_SIZE):
                    result[y][x] += grid[y][x]
        return result

    def normalize_grid(grid):
        """归一化到 0-100"""
        max_val = max(max(row) for row in grid)
        if max_val > 0:
            return [[round(v / max_val * 100) for v in row] for row in grid]
        return grid

    for region in heatmap_data['data']:
        region_dir = os.path.join(heatmap_dir, region)
        schools = heatmap_data['data'][region]

        # 位置热力图：按兵种聚合所有学校
        # robot_type -> {'red': [grids], 'blue': [grids]}
        pos_aggregated = {}
        for school, robots in schools.items():
            for rtype, sides in robots.items():
                if rtype not in pos_aggregated:
                    pos_aggregated[rtype] = {'red': [], 'blue': []}
                if isinstance(sides, dict) and 'red' in sides:
                    pos_aggregated[rtype]['red'].append(sides['red'])
                    pos_aggregated[rtype]['blue'].append(sides['blue'])

        all_encoded = {}
        for rtype, sides in pos_aggregated.items():
            red = normalize_grid(sum_grids(sides['red']))
            blue = normalize_grid(sum_grids(sides['blue']))
            all_encoded[rtype] = {'red': encode_grid(red), 'blue': encode_grid(blue)}

        if all_encoded:
            with open(os.path.join(region_dir, '_all.json'), 'w', encoding='utf-8') as f:
                json.dump(all_encoded, f, ensure_ascii=False, separators=(',', ':'))
            agg_files += 1

        # 进攻/受击热力图：按兵种聚合所有学校
        for heatmap_type in ('attack', 'damage'):
            suffix = f'_{heatmap_type}'
            type_aggregated = {}  # robot_type -> {'red': [grids], 'blue': [grids]}
            for school_data in event_heatmap_data.get(region, {}).values():
                robot_types_data = school_data.get(heatmap_type, {})
                for rtype, sides in robot_types_data.items():
                    if rtype not in type_aggregated:
                        type_aggregated[rtype] = {'red': [], 'blue': []}
                    type_aggregated[rtype]['red'].append(sides['red'])
                    type_aggregated[rtype]['blue'].append(sides['blue'])

            for rtype, sides in type_aggregated.items():
                red = normalize_grid(sum_grids(sides['red']))
                blue = normalize_grid(sum_grids(sides['blue']))
                encoded = {'red': encode_grid(red), 'blue': encode_grid(blue)}
                with open(os.path.join(region_dir, f'_all{suffix}_{rtype}.json'), 'w', encoding='utf-8') as f:
                    json.dump(encoded, f, ensure_ascii=False, separators=(',', ':'))
                agg_files += 1

    print(f"已保存 {agg_files} 个聚合文件")

    conn.close()
    print("\n导出完成!")


if __name__ == '__main__':
    main()
