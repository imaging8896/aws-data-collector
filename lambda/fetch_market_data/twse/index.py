from datetime import datetime, date
from decimal import Decimal

from curl_cffi import requests


def get_indexes(data_date: date):
    url = f"https://app.twse.com.tw/v2/api/zh/exchange/indexInfo?source=14b22ffaf9f5040559c8c9d3c6f48833&lang=zh&date={data_date.isoformat().replace('-', '')}"

    response = requests.get(url, impersonate="chrome")

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")
    
    data = response.json()

    print(f"Got data {data['api_name']}")
    # "items": [
    #     {
    #         "idx_name": "寶島股價指數",
    #         "idx_today": "33743.18",
    #         "idx_mark": "-",
    #         "idx_diff": "75.87",
    #         "idx_diff_percent": "0.22",
    #         "trn_date": "20260109",
    #         "show_seq": "0"
    #     },
    return {
        index_data['idx_name'].strip().replace('指數', ''): {
            'value': Decimal(index_data['idx_today'].replace(',', '')),
            'date': datetime.strptime(index_data['trn_date'], '%Y%m%d').date().isoformat(),
            'diff': Decimal(index_data['idx_mark'] + index_data['idx_diff'].replace(',', '')),
            'diff_percent': Decimal(index_data['idx_mark'] + index_data['idx_diff_percent'].replace(',', '')),
        }
        for index_data in data['items']
    }
