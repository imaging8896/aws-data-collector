import enum

from dataclasses import dataclass
from datetime import datetime, date
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

    response = requests.get(url, impersonate="chrome")

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")
    
    data = response.json()
    
    if data.get('statusCode') != 200 or data.get('message') != 'OK':
        raise Exception(f"API error: {data}")
    
    data = data['data']
    if len(data) != len(indexes):
        raise Exception(f"Returned data length {len(data)}\n{data}\ndoes not match requested indexes length {len(indexes)}")

    result = {}
    for request_index, response_data in zip(indexes, data):
        key = str(request_index)
        if index_data := response_data.get(key):
            if index_data.get('s') != 'ok':
                raise Exception(f"Data for index {key} returned status\n{index_data}\nin\n{data}")
            
            data_dates = [date.fromtimestamp(time).isoformat() for time in index_data['t']]
    
            opening_prices = [Decimal(str(price)) for price in index_data['o']]
            if len(opening_prices) != len(data_dates):
                raise Exception(f"Data length mismatch for index {key}: dates({len(data_dates)}) vs openings({len(opening_prices)})\n{data}")
    
            closing_prices = [Decimal(str(price)) for price in index_data['c']]
            if len(closing_prices) != len(data_dates):
                raise Exception(f"Data length mismatch for index {key}: dates({len(data_dates)}) vs closings({len(closing_prices)})\n{data}")

            high_prices = [Decimal(str(price)) for price in index_data['h']]
            if len(high_prices) != len(data_dates):
                raise Exception(f"Data length mismatch for index {key}: dates({len(data_dates)}) vs highs({len(high_prices)})\n{data}")

            low_prices = [Decimal(str(price)) for price in index_data['l']]
            if len(low_prices) != len(data_dates):
                raise Exception(f"Data length mismatch for index {key}: dates({len(data_dates)}) vs lows({len(low_prices)})\n{data}")

            volumes = [Decimal(str(price)) * Decimal(1000) for price in index_data['v']]
            if len(volumes) != len(data_dates):
                raise Exception(f"Data length mismatch for index {key}: dates({len(data_dates)}) vs volumes({len(volumes)})\n{data}")

            turnovers = [Decimal(str(turnover)) for turnover in index_data['turnover']]
            if len(turnovers) != len(data_dates):
                raise Exception(f"Data length mismatch for index {key}: dates({len(data_dates)}) vs turnover({len(turnovers)})\n{data}")

            # 'vwap' are also available but not used here
            percent = Decimal(str(index_data['quote']['220064'])) if index_data['quote']['220064'] is not None else None
            avg = Decimal(str(index_data['quote']['3404'])) if index_data['quote']['3404'] is not None else None
            diff = Decimal(str(index_data['quote']['11'])) if index_data['quote']['11'] is not None else None
            name = index_data['quote']['200009']

            result[request_index] = {
                "name": name,
                "data": list(
                    zip(
                        data_dates,
                        opening_prices,
                        closing_prices,
                        high_prices,
                        low_prices,
                        volumes,
                        turnovers, # 成交金額
                        strict=True,
                    )
                )
            }
        else:
            raise Exception(f"Missing data for index {key} in response: {data}")
    return result
