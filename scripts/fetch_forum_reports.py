#!/usr/bin/env python3
"""Fetch open-source reports from RoboMaster BBS matching top schools per robot type."""

import json
import os
import sys
import time
from datetime import datetime

import requests

API_BASE = "https://bbs.robomaster.com/developers-server/rest"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
ROBOT_DATA_FILE = os.path.join(DATA_DIR, "robot_data_2026.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "forum_reports_2026.json")

TYPE_NAMES = {
    "Infantry": "步兵",
    "Hero": "英雄",
    "Sapper": "工程",
    "Airplane": "无人机",
    "Guard": "哨兵",
    "Radar": "雷达",
    "Dart": "飞镖",
}

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def get_top_schools(robot_data, top_n=9):
    """Get top N schools per robot type from robot data."""
    school_types = {}  # {school_name: set(type_cn_names)}
    cfg_excluded = []  # no excluded zones for 2026

    for zone in robot_data.get("zones", []):
        if zone.get("zoneId") in cfg_excluded:
            continue
        for team in zone.get("teams", []):
            college = team.get("collegeName", "")
            for robot in team.get("robots", []):
                rtype = robot.get("type", "")
                if rtype in TYPE_NAMES:
                    if college not in school_types:
                        school_types[college] = set()
                    school_types[college].add(TYPE_NAMES[rtype])

    # For each type, get top N schools by fetching ladder ranking
    # Simplified: collect all schools that appear in any zone
    result = {}  # {type_cn: [school_names]}
    for type_key, type_cn in TYPE_NAMES.items():
        schools = []
        for zone in robot_data.get("zones", []):
            if zone.get("zoneId") in cfg_excluded:
                continue
            for team in zone.get("teams", []):
                college = team.get("collegeName", "")
                if any(r.get("type") == type_key for r in team.get("robots", [])):
                    if college not in schools:
                        schools.append(college)
        result[type_cn] = schools

    return result


def fetch_all_articles():
    """Fetch all articles from BBS API, paginating."""
    articles = []
    page_no = 1
    page_size = 100
    total = None

    while True:
        print(f"  Fetching page {page_no}...")
        try:
            resp = requests.post(
                f"{API_BASE}/posts/list",
                json={
                    "filter": {"category": "ARTICLE"},
                    "pageSize": page_size,
                    "pageNo": page_no,
                },
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  Error fetching page {page_no}: {e}")
            break

        if not data.get("success"):
            print(f"  API returned error: {data.get('message')}")
            break

        result_data = data.get("data", {})
        if total is None:
            total = result_data.get("total", 0)
            print(f"  Total articles: {total}")

        page_articles = result_data.get("list", [])
        if not page_articles:
            break

        articles.extend(page_articles)
        print(f"  Got {len(page_articles)} articles (total so far: {len(articles)})")

        if len(articles) >= total:
            break

        page_no += 1
        time.sleep(0.3)

    return articles


def match_articles(articles, school_type_map):
    """Match articles to school+type combinations by keyword search."""
    reports = {}  # {school_name: {type_cn: [article_info]}}

    for article in articles:
        title = article.get("title", "") or ""
        intro = article.get("introduction", "") or ""
        text = title + " " + intro
        article_id = article.get("id")
        if not article_id:
            continue
        if article.get("authorNickname") == "粉丝大管家":
            continue

        for type_cn, schools in school_type_map.items():
            if type_cn not in text:
                continue
            for school in schools:
                if school not in text:
                    continue
                # Both school name and type name found in text
                if school not in reports:
                    reports[school] = {}
                if type_cn not in reports[school]:
                    reports[school][type_cn] = []

                date_str = article.get("createAt", "")
                if date_str:
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        date_str = dt.strftime("%Y-%m-%d")
                    except Exception:
                        pass

                reports[school][type_cn].append({
                    "title": title,
                    "url": f"https://bbs.robomaster.com/article/{article_id}",
                    "author": article.get("authorNickname", ""),
                    "date": date_str,
                })

    return reports


def main():
    print("Loading robot data...")
    with open(ROBOT_DATA_FILE, "r", encoding="utf-8") as f:
        robot_data = json.load(f)

    print("Extracting top schools per type...")
    school_type_map = get_top_schools(robot_data)
    total_schools = len(set(s for schools in school_type_map.values() for s in schools))
    print(f"  {total_schools} unique schools across {len(school_type_map)} robot types")

    print("Fetching articles from BBS...")
    articles = fetch_all_articles()
    print(f"Fetched {len(articles)} articles total")

    print("Matching articles...")
    reports = match_articles(articles, school_type_map)

    # Count matches
    match_count = sum(len(t) for s in reports.values() for t in s.values())
    print(f"Found {match_count} matching reports for {len(reports)} schools")

    output = {"reports": reports}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
