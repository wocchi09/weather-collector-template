"""
毎晩じっこうされる天気データ収集スクリプト。

やっていること:
  1. Open-Meteo（むりょう・APIキー不要・商用OK）から天気予報をとる
  2. ひつような項目だけとりだす
  3. data/weather.csv に1行ずつ追記する（ついきモード）

★ 自分のようとにあわせて変えるのは主に CONFIG のところだけ。
"""

import csv
import datetime
import os
import sys
import urllib.request
import urllib.parse
import json

# ───────────────────────────────────────────────
#  CONFIG : ここだけ自分ようにかえればOK
# ───────────────────────────────────────────────
CONFIG = {
    # あつめたい地点（緯度・経度）。下は東京。
    # ほかの地点にしたいときは緯度経度をかえるだけ。
    "latitude": 35.6895,
    "longitude": 139.6917,
    "place_name": "Tokyo",
    # とりたい項目（Open-Meteo の daily パラメータ）
    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
    "timezone": "Asia/Tokyo",
    # ほぞんさきの CSV ファイル
    "csv_path": "data/weather.csv",
}

API_URL = "https://api.open-meteo.com/v1/forecast"


def build_url(cfg: dict) -> str:
    """CONFIG から API の URL を組み立てる。"""
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "daily": cfg["daily"],
        "timezone": cfg["timezone"],
        "forecast_days": 1,  # 今日ぶんだけ
    }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def fetch_weather(url: str) -> dict:
    """API をたたいて JSON をとってくる。"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "weather-collector-template/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def extract_rows(data: dict, place_name: str) -> list[dict]:
    """API のこたえから、CSV1行ぶんのデータをとりだす。"""
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    rows = []
    for i, date in enumerate(dates):
        rows.append(
            {
                "date": date,
                "place": place_name,
                "temp_max": daily.get("temperature_2m_max", [None])[i],
                "temp_min": daily.get("temperature_2m_min", [None])[i],
                "precipitation": daily.get("precipitation_sum", [None])[i],
                "collected_at": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
            }
        )
    return rows


def append_to_csv(rows: list[dict], csv_path: str) -> None:
    """CSV にデータを追記する。ファイルがなければヘッダーもつける。"""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    file_exists = os.path.exists(csv_path)
    fieldnames = [
        "date",
        "place",
        "temp_max",
        "temp_min",
        "precipitation",
        "collected_at",
    ]
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    cfg = CONFIG
    print(f"[1/3] {cfg['place_name']} の天気データを取得します…")
    url = build_url(cfg)
    try:
        data = fetch_weather(url)
    except Exception as e:
        print(f"エラー: データ取得にしっぱいしました -> {e}", file=sys.stderr)
        return 1

    print("[2/3] データを整形します…")
    rows = extract_rows(data, cfg["place_name"])
    if not rows:
        print("エラー: 取得できたデータが空でした。", file=sys.stderr)
        return 1

    print(f"[3/3] {cfg['csv_path']} に {len(rows)} 件を追記します…")
    append_to_csv(rows, cfg["csv_path"])
    print("かんりょう ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
