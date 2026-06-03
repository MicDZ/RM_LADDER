#!/usr/bin/env python3
"""Build match history JSON from rm-schedule history_match.json with college name normalization."""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
INPUT_FILE = os.path.join(DATA_DIR, "history_match_raw.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "match_history.json")

# Phase 1: exact-match renames (college name changes, abbreviations, joint programs)
EXACT_NORMALIZE = {
    "华南理工大学广州学院": "广州城市理工学院",
    "佛山科学技术学院": "佛山大学",
    "深圳职业技术学院": "深圳职业技术大学",
    "福建工程学院": "福建理工大学",
    "中国人民解放军国防科技大学": "国防科技大学",
    "西交利物浦大学&利物浦大学": "西交利物浦大学",
    "西交利物浦大学&University of Liverpool": "西交利物浦大学",
    "合肥工业大学宣城校区": "合肥工业大学（宣城校区）",
    "桂林电子科技大学信息科技学院": "桂林信息科技学院",
    "北京理工大学（珠海）": "北京理工大学珠海学院",
    "厦门大学嘉庚学院&厦门大学漳州校区": "厦门大学嘉庚学院",
    "江苏城市职业学院": "江苏城市职业学院",
    # Normalize half-width parens in specific known cases
    "合肥工业大学(宣城校区)": "合肥工业大学（宣城校区）",
}

# Phase 2: normalize half-width parens to full-width
HALF_TO_FULL = str.maketrans("()", "（）")


def normalize_parens(name):
    """Convert half-width parentheses to full-width."""
    return name.translate(HALF_TO_FULL)


def normalize(name):
    """Normalize a college name: exact map first, then paren normalization."""
    if not name:
        return name
    name = EXACT_NORMALIZE.get(name, name)
    name = normalize_parens(name)
    return name


def main():
    # Load raw data
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    print(f"Loaded {len(raw)} raw match records")

    # Build per-college match history
    from collections import defaultdict
    schools = defaultdict(lambda: defaultdict(list))

    for match in raw:
        season = str(match.get("season", ""))
        zone = match.get("zone", "")
        group = match.get("group", "")
        order = match.get("order", 0)
        order_number = match.get("orderNumber", 0)
        blue_college = normalize(match.get("blueCollegeName", ""))
        red_college = normalize(match.get("redCollegeName", ""))
        blue_team = match.get("blueTeamName", "")
        red_team = match.get("redTeamName", "")
        blue_wins = match.get("blueSideWinGameCount", 0)
        red_wins = match.get("redSideWinGameCount", 0)

        # Determine match stage label from group name
        # Groups like "小组赛A", "1/4决赛", "半决赛", "决赛" etc.
        stage = group

        # Blue side entry
        if blue_college:
            if blue_wins > red_wins:
                result = "win"
            elif blue_wins < red_wins:
                result = "loss"
            else:
                result = "draw"
            schools[blue_college][season].append({
                "opponent": red_college,
                "result": result,
                "score": f"{blue_wins}:{red_wins}",
                "zone": zone,
                "group": stage,
                "order": str(order),
                "opponentTeam": red_team,
                "ownTeam": blue_team,
            })

        # Red side entry
        if red_college:
            if red_wins > blue_wins:
                result = "win"
            elif red_wins < blue_wins:
                result = "loss"
            else:
                result = "draw"
            schools[red_college][season].append({
                "opponent": blue_college,
                "result": result,
                "score": f"{red_wins}:{blue_wins}",
                "zone": zone,
                "group": stage,
                "order": str(order),
                "opponentTeam": blue_team,
                "ownTeam": red_team,
            })

    # Build output structure
    all_seasons = set()
    for school_data in schools.values():
        for season in school_data:
            all_seasons.add(season)
    all_seasons = sorted(all_seasons, key=int)

    output_schools = {}
    summaries = {}

    for college_name in sorted(schools.keys()):
        school_data = schools[college_name]
        seasons_list = []
        for season in sorted(school_data.keys(), key=int):
            matches = sorted(school_data[season], key=lambda m: m["order"])
            seasons_list.append({
                "season": season,
                "matches": matches,
            })

        output_schools[college_name] = seasons_list

        # Compute summary
        total_wins = 0
        total_losses = 0
        total_draws = 0
        per_season = {}

        for season_entry in seasons_list:
            season = season_entry["season"]
            wins = sum(1 for m in season_entry["matches"] if m["result"] == "win")
            losses = sum(1 for m in season_entry["matches"] if m["result"] == "loss")
            draws = sum(1 for m in season_entry["matches"] if m["result"] == "draw")
            total_wins += wins
            total_losses += losses
            total_draws += draws
            per_season[season] = {"wins": wins, "losses": losses, "draws": draws}

        summaries[college_name] = {
            "totalWins": total_wins,
            "totalLosses": total_losses,
            "totalDraws": total_draws,
            "perSeason": per_season,
        }

    output = {
        "schools": output_schools,
        "summary": summaries,
        "seasons": all_seasons,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Written {len(output_schools)} colleges to {OUTPUT_FILE}")
    print(f"Seasons: {all_seasons}")
    total_matches = sum(
        sum(len(season_matches) for season_matches in school_seasons.values())
        for school_seasons in schools.values()
    )
    print(f"Total match entries (both sides): {total_matches}")

    # Print some stats
    print(f"\nTop 10 colleges by match count:")
    sorted_colleges = sorted(summaries.items(), key=lambda x: x[1]["totalWins"] + x[1]["totalLosses"] + x[1]["totalDraws"], reverse=True)
    for name, summary in sorted_colleges[:10]:
        total = summary["totalWins"] + summary["totalLosses"] + summary["totalDraws"]
        print(f"  {name}: {summary['totalWins']}W {summary['totalLosses']}L {summary['totalDraws']}D ({total} matches)")


if __name__ == "__main__":
    main()
