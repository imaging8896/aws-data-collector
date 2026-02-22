from datetime import date
from decimal import Decimal

from curl_cffi import requests


def get_stock_group_trade(data_date: date):
    data_date_str_without_dash = data_date.isoformat().replace("-", "")
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/BFIAMU?date={data_date_str_without_dash}&response=json"

    response = requests.get(url, impersonate="chrome")

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")

    data = response.json()

    if data.get("stat") == "很抱歉，沒有符合條件的資料!":
        return

    if data.get("stat") != "OK":
        raise Exception(f"API error:\n{data}")

    if data.get("date") != data_date_str_without_dash:
        raise Exception(f"Returned data date {data.get('date')} does not match requested date {data_date_str_without_dash}\n{data}")

    print(f"Got data {data['title']}")
    # "data": [
    # [
    #     "水泥類指數          ",
    #     "37,481,195",
    #     "939,476,487",
    #     "10,158",
    #     "0.65"
    # ],
    # [
    #     "食品類指數          ",
    #     "28,112,275",
    #     "2,011,087,362",
    #     "13,147",
    #     "0.41"
    # ],

    return {
        _process_name(name): {
            "shares": Decimal(shares.replace(",", "")),
            "amount": Decimal(amount.replace(",", "")),
            "transactions": Decimal(transactions.replace(",", "")),
        }
        for name, shares, amount, transactions, _ in data["data"]
    }


def _process_name(raw_name: str) -> str:
    raw_name = raw_name.strip().replace("指數", "")
    if raw_name == "航運業類":
        return "航運類"
    return raw_name
