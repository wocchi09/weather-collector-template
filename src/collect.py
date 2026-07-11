"""
毎晩実行される天気データ収集スクリプト（47都道府県フル対応・天気概況つき）。

やっていること:
  1. PREFECTURES に「名前と座標」をセットで持っておく（地名検索APIを使わない）
  2. その座標で天気予報（Open-Meteo・無料・APIキー不要・商用OK）を取得
  3. 気温・降水量に加え、天気概況（晴れ/くもり/雨など）も記録
  4. data/weather.csv に47行ずつ追記する

★ 集める地点を変えたいときは、PREFECTURES に (名前, 緯度, 経度) を足す/消すだけ。

座標データ出典: みんなの知識 ちょっと便利帳「都道府県庁所在地 緯度経度データ」
（世界測地系WGS84・県庁舎の位置）
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
#  CONFIG : ここだけ自分用に変えればOK
# ───────────────────────────────────────────────

# 集めたい地点を (名前, 緯度, 経度) のセットで並べる。
# 座標をここに埋め込んでおくため、地名検索APIを使わない＝安定して動作する。
PREFECTURES = [
    ("北海道", 43.064310, 141.346879),
    ("青森県", 40.824589, 140.740548),
    ("岩手県", 39.703526, 141.152696),
    ("宮城県", 38.268579, 140.872072),
    ("秋田県", 39.718626, 140.102381),
    ("山形県", 38.240434, 140.363690),
    ("福島県", 37.750029, 140.467771),
    ("茨城県", 36.341737, 140.446824),
    ("栃木県", 36.565912, 139.883592),
    ("群馬県", 36.390688, 139.060453),
    ("埼玉県", 35.857033, 139.649012),
    ("千葉県", 35.604560, 140.123154),
    ("東京都", 35.689501, 139.691722),
    ("神奈川県", 35.447734, 139.642537),
    ("新潟県", 37.902451, 139.023245),
    ("富山県", 36.695265, 137.211305),
    ("石川県", 36.594606, 136.625669),
    ("福井県", 36.065209, 136.221720),
    ("山梨県", 35.664108, 138.568455),
    ("長野県", 36.651306, 138.180904),
    ("岐阜県", 35.391174, 136.723657),
    ("静岡県", 34.976944, 138.383056),
    ("愛知県", 35.180209, 136.906582),
    ("三重県", 34.730278, 136.508611),
    ("滋賀県", 35.004513, 135.868568),
    ("京都府", 35.021242, 135.755613),
    ("大阪府", 34.686344, 135.520037),
    ("兵庫県", 34.691257, 135.183078),
    ("奈良県", 34.685274, 135.832861),
    ("和歌山県", 34.226111, 135.167500),
    ("鳥取県", 35.503449, 134.238261),
    ("島根県", 35.472293, 133.050520),
    ("岡山県", 34.661739, 133.935032),
    ("広島県", 34.396558, 132.459646),
    ("山口県", 34.186041, 131.470654),
    ("徳島県", 34.065761, 134.559286),
    ("香川県", 34.340112, 134.043291),
    ("愛媛県", 33.841642, 132.765682),
    ("高知県", 33.559722, 133.531111),
    ("福岡県", 33.606389, 130.417968),
    ("佐賀県", 33.249351, 130.298792),
    ("長崎県", 32.750040, 129.867251),
    ("熊本県", 32.789800, 130.741584),
    ("大分県", 33.238130, 131.612645),
    ("宮崎県", 31.911034, 131.423887),
    ("鹿児島県", 31.560171, 130.558025),
    ("沖縄県", 26.212445, 127.680922),
]

CONFIG = {
    # 取りたい項目（Open-Meteo の daily パラメータ）
    # weather_code = 天気の種類を表す数字
    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
    "timezone": "Asia/Tokyo",
    "csv_path": "data/weather.csv",
}

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo の weather_code（WMO天気コード）を、日本語の天気概況に変換する表。
# 参考: https://open-meteo.com/en/docs （WMO Weather interpretation codes）
WEATHER_CODE_JA = {
    0: "快晴",
    1: "晴れ", 2: "晴れ時々くもり", 3: "くもり",
    45: "霧", 48: "霧(着氷)",
    51: "霧雨(弱)", 53: "霧雨", 55: "霧雨(強)",
    56: "着氷性霧雨(弱)", 57: "着氷性霧雨(強)",
    61: "雨(弱)", 63: "雨", 65: "雨(強)",
    66: "着氷性の雨(弱)", 67: "着氷性の雨(強)",
    71: "雪(弱)", 73: "雪", 75: "雪(強)", 77: "雪(あられ)",
    80: "にわか雨(弱)", 81: "にわか雨", 82: "にわか雨(激)",
    85: "にわか雪(弱)", 86: "にわか雪(強)",
    95: "雷雨", 96: "雷雨(ひょう弱)", 99: "雷雨(ひょう強)",
}


def weather_text(code) -> str:
    """天気コード（数字）を日本語に変換。未知のコードはそのまま数字を返す。"""
    if code is None:
        return "不明"
    return WEATHER_CODE_JA.get(int(code), f"コード{code}")


def fetch_weather(lat: float, lon: float, cfg: dict) -> dict:
    """座標から天気予報を取得する。"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": cfg["daily"],
        "timezone": cfg["timezone"],
        "forecast_days": 1,
    }
    url = f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "weather-collector-template/3.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def extract_row(data: dict, place_name: str) -> dict | None:
    """天気予報の結果から、CSV1行分のデータを取り出す。"""
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    if not dates:
        return None
    code = daily.get("weather_code", [None])[0]
    return {
        "date": dates[0],
        "place": place_name,
        "weather": weather_text(code),
        "temp_max": daily.get("temperature_2m_max", [None])[0],
        "temp_min": daily.get("temperature_2m_min", [None])[0],
        "precipitation": daily.get("precipitation_sum", [None])[0],
        "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def append_to_csv(rows: list[dict], csv_path: str) -> None:
    """CSVにデータを追記する。ファイルがなければヘッダーも付ける。"""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    file_exists = os.path.exists(csv_path)
    fieldnames = [
        "date", "place", "weather",
        "temp_max", "temp_min", "precipitation", "collected_at",
    ]
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fetch_with_retry(lat, lon, cfg, tries=3):
    """接続がタイムアウトしても数回リトライする。"""
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            return fetch_weather(lat, lon, cfg)
        except Exception as e:
            last_err = e
            time.sleep(1.0 * attempt)  # 少しずつ待ち時間を延ばして再挑戦
    raise last_err


def main() -> int:
    cfg = CONFIG
    rows = []
    failed = []
    total = len(PREFECTURES)

    for i, (place, lat, lon) in enumerate(PREFECTURES, start=1):
        print(f"[{i}/{total}] {place} …", end=" ")
        try:
            data = fetch_with_retry(lat, lon, cfg)
            row = extract_row(data, place)
            if row is None:
                print("天気データが空でした（スキップ）")
                failed.append(place)
                continue
            rows.append(row)
            print(f"OK ({row['weather']} / 最高{row['temp_max']}℃ / 最低{row['temp_min']}℃)")
        except Exception as e:
            print(f"エラー: {e}（スキップ）")
            failed.append(place)
        time.sleep(0.3)  # APIに連続アクセスしすぎない

    if not rows:
        print("エラー: 1件もデータが取得できませんでした。", file=sys.stderr)
        return 1

    append_to_csv(rows, cfg["csv_path"])
    print(f"\n完了 ✅  {len(rows)}件を {cfg['csv_path']} に追記しました。")
    if failed:
        print(f"※ 取得できなかった地点: {', '.join(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
