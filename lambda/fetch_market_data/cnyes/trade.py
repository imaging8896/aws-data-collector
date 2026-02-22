import enum
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from curl_cffi import requests

# Alternative
# https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=html&date=20260106&stockNo=2330


@dataclass
class Index:
    @enum.unique
    class Location(enum.Enum):
        TW = "TWS"

    @enum.unique
    class Type(enum.Enum):
        INDEX = "INDEX"
        STOCK = "STOCK"

    symbol: str
    location: Location
    type: Type

    def __str__(self) -> str:
        return f"{self.location.value}:{self.symbol}:{self.type.value}"

    def __hash__(self) -> int:
        return hash((self.symbol, self.location.value, self.type))

    @classmethod
    def tw_stock(cls, stock_id):
        return cls(symbol=stock_id, location=Index.Location.TW, type=Index.Type.STOCK)

    @classmethod
    def tw_index(cls):
        return cls(symbol="TSE01", location=Index.Location.TW, type=Index.Type.INDEX)


def get_trades(indexes: list[Index], from_dt: datetime, to_dt: datetime):
    symbols = ",".join(str(index) for index in indexes)
    url = f"https://ws.api.cnyes.com/ws/api/v1/charting/histories?symbols={symbols}&from={int(to_dt.timestamp())}&to={int(from_dt.timestamp())}&resolution=D"
    if from_dt.year <= 2021 or to_dt.year <= 2021:
        if len(indexes) > 1:
            raise Exception("CNYES API does not support multiple symbols for history endpoint")
        url = f"https://ws.api.cnyes.com/ws/api/v1/charting/history?resolution=D&symbol={symbols}&from={int(to_dt.timestamp())}&to={int(from_dt.timestamp())}&quote=1"
    response = requests.get(url, impersonate="chrome")

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")

    data = response.json()

    if data.get("statusCode") != 200 or data.get("message") != "OK":
        raise Exception(f"API error: {data}")

    data = data["data"]
    result = {}
    if isinstance(data, list):
        index_iter = iter(indexes)
        for response_data in data:
            for index in index_iter:
                key = str(index)
                if key in response_data:
                    result[index] = _get_data(response_data[key], data)
                    break
                else:
                    print(f"[ERROR] Missing data for index {key} in response: {data}")
    else:
        result[indexes[0]] = _get_data(data, data)

    return result


def _get_data(index_data, all_data):
    if index_data.get("s") != "ok":
        raise Exception(f"Data for index returned status\n{index_data}\nin\n{all_data}")

    data_dates = [date.fromtimestamp(time).isoformat() for time in index_data["t"]]

    opening_prices = [Decimal(str(price)) for price in index_data["o"]]
    if len(opening_prices) != len(data_dates):
        raise Exception(f"Data length mismatch: dates({len(data_dates)}) vs openings({len(opening_prices)})\n{all_data}")

    closing_prices = [Decimal(str(price)) for price in index_data["c"]]
    if len(closing_prices) != len(data_dates):
        raise Exception(f"Data length mismatch: dates({len(data_dates)}) vs closings({len(closing_prices)})\n{all_data}")
    high_prices = [Decimal(str(price)) for price in index_data["h"]]
    if len(high_prices) != len(data_dates):
        raise Exception(f"Data length mismatch: dates({len(data_dates)}) vs highs({len(high_prices)})\n{all_data}")

    low_prices = [Decimal(str(price)) for price in index_data["l"]]
    if len(low_prices) != len(data_dates):
        raise Exception(f"Data length mismatch: dates({len(data_dates)}) vs lows({len(low_prices)})\n{all_data}")

    if "turnover" in index_data:
        turnovers = [Decimal(str(turnover)) for turnover in index_data["turnover"]]
        volumes = [Decimal(str(price)) * Decimal(1000) for price in index_data["v"]]
    else:
        turnovers = [Decimal(str(turnover)) for turnover in index_data["v"]]
        volumes = [None] * len(data_dates)

    if len(volumes) != len(data_dates):
        raise Exception(f"Data length mismatch: dates({len(data_dates)}) vs volumes({len(volumes)})\n{all_data}")

    if len(turnovers) != len(data_dates):
        raise Exception(f"Data length mismatch: dates({len(data_dates)}) vs turnover({len(turnovers)})\n{all_data}")

    # Note: 'vwap', 'percent' (220064), 'avg' (3404), 'diff' (11) are also available in quote but not used here
    name = index_data["quote"]["200009"]

    return {
        "name": name,
        "data": list(
            zip(
                data_dates,
                opening_prices,
                closing_prices,
                high_prices,
                low_prices,
                volumes,
                turnovers,  # 成交金額
                strict=True,
            )
        ),
    }
