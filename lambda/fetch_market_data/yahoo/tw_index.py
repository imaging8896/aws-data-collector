from datetime import datetime
from decimal import Decimal

from curl_cffi import requests


def get_tw_indexes():
    start_timestamp = 1041379201  # 2003-01-01 before this there is no volume data
    end_timestamp = int(datetime.now().timestamp())

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?events=capitalGain%7Cdiv%7Csplit&formatted=true&includeAdjustedClose=true&interval=1d&period1={start_timestamp}&period2={end_timestamp}&symbol=%5ETWII&userYfid=true&lang=zh-Hant-HK&region=HK"

    response = requests.get(url, impersonate="chrome")

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")

    data = response.json()
    print(f"Got data {data['chart']['error']=}")

    data = data["chart"]["result"][0]
    timestamps = [datetime.fromtimestamp(ts).date().isoformat() for ts in data["timestamp"]]

    adjcloses = [
        Decimal(x) if x is not None else None for x in data["indicators"]["adjclose"][0]["adjclose"]
    ]  # 收市價因拆股和股息及/或資本盈利分派而經過調整。

    closes = [Decimal(x) if x is not None else None for x in data["indicators"]["quote"][0]["close"]]
    highs = [Decimal(x) if x is not None else None for x in data["indicators"]["quote"][0]["high"]]
    lows = [Decimal(x) if x is not None else None for x in data["indicators"]["quote"][0]["low"]]
    opens = [Decimal(x) if x is not None else None for x in data["indicators"]["quote"][0]["open"]]
    volumes = [x if x != 0 else None for x in data["indicators"]["quote"][0]["volume"]]
    volumes = [Decimal(x) if x is not None else None for x in volumes]

    if not (len(timestamps) == len(adjcloses) == len(closes) == len(highs) == len(lows) == len(opens) == len(volumes)):
        raise Exception(f"Data length mismatch among fields\n{data}")

    return [
        x
        for x in zip(
            timestamps,
            opens,
            closes,
            highs,
            lows,
            volumes,
            adjcloses,
            strict=True,
        )
        if x[1] is not None
    ]
