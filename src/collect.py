"""
毎晩実行される天気データ収集スクリプト（47都道府県フル対応版）。

やっていること:
  1. PREFECTURES に並べた都道府県名から、Open-Meteo の Geocoding API で
     座標（緯度・経度）を自動でしらべる ← 座標を手打ちしなくていい
  2. その座標で天気予報（Open-Meteo・むりょう・APIキー不要・商用OK）をとる
  3. data/weather.csv に47行ずつ追記する

★ 集める地点をかえたいときは、PREFECTURES のリストを書きかえるだけ。
  （都道府県じゃなく「札幌」「延岡」など市町村名でもOK）
"""

import csv
import datetime
import os
import sys
import time
import urllib.request
import urllib.parse
import json

# ───────────────────────────────────────────────
#  CONFIG : ここだけ自分ようにかえればOK
# ───────────────────────────────────────────────

# 集めたい地点の名前をならべるだけ。座標は自動でしらべます。
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

CONFIG = {
    # とりたい項目（Open-Meteo の daily パラメータ）
    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
    "timezone": "Asia/Tokyo",
    # ほぞんさきの CSV ファイル
    "csv_path": "data/weather.csv",
}

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def _get_json(url: str) -> dict:
    """URL をたたいて JSON をとってくる（共通処理）。"""
    req = urllib.request.Request(
        url, headers={"User-Agent": "weather-collector-template/2.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def geocode(place_name: str) -> tuple[float, float] | None:
    """地名から緯度・経度をしらべる。見つからなければ None。"""
    params = {"name": place_name, "count": 1, "language": "ja", "country": "JP"}
    url = f"{GEOCODE_URL}?{urllib.parse.urlencode(params)}"
    data = _get_json(url)
    results = data.get("results")
    if not results:
        return None
    top = results[0]
    return (top["latitude"], top["longitude"])


def fetch_weather(lat: float, lon: float, cfg: dict) -> dict:
    """座標から天気予報をとってくる。"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": cfg["daily"],
        "timezone": cfg["timezone"],
        "forecast_days": 1,
    }
    url = f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"
    return _get_json(url)


def extract_row(data: dict, place_name: str) -> dict | None:
    """天気予報のこたえから、CSV1行ぶんのデータをとりだす。"""
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    if not dates:
        return None
    return {
        "date": dates[0],
        "place": place_name,
        "temp_max": daily.get("temperature_2m_max", [None])[0],
        "temp_min": daily.get("temperature_2m_min", [None])[0],
        "precipitation": daily.get("precipitation_sum", [None])[0],
        "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def append_to_csv(rows: list[dict], csv_path: str) -> None:
    """CSV にデータを追記する。ファイルがなければヘッダーもつける。"""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    file_exists = os.path.exists(csv_path)
    fieldnames = [
        "date", "place", "temp_max", "temp_min", "precipitation", "collected_at",
    ]
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    cfg = CONFIG
    rows = []
    failed = []
    total = len(PREFECTURES)

    for i, place in enumerate(PREFECTURES, start=1):
        print(f"[{i}/{total}] {place} …", end=" ")
        try:
            coords = geocode(place)
            if coords is None:
                print("座標が見つかりませんでした（スキップ）")
                failed.append(place)
                continue
            lat, lon = coords
            data = fetch_weather(lat, lon, cfg)
            row = extract_row(data, place)
            if row is None:
                print("天気データが空でした（スキップ）")
                failed.append(place)
                continue
            rows.append(row)
            print(f"OK (最高{row['temp_max']}℃ / 最低{row['temp_min']}℃)")
        except Exception as e:
            print(f"エラー: {e}（スキップ）")
            failed.append(place)
        # APIに連続アクセスしすぎないよう、少し間をあける
        time.sleep(0.3)

    if not rows:
        print("エラー: 1件もデータが取れませんでした。", file=sys.stderr)
        return 1

    append_to_csv(rows, cfg["csv_path"])
    print(f"\nかんりょう ✅  {len(rows)}件を {cfg['csv_path']} に追記しました。")
    if failed:
        print(f"※ 取得できなかった地点: {', '.join(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
