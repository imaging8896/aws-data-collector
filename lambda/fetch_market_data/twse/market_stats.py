from datetime import date

from curl_cffi import requests


def get_market_stats(data_date: date) -> dict | None:
    """
    Fetch Taiwan stock market statistics (上漲/下跌/平盤家數) from TWSE.

    Args:
        data_date: The date to fetch data for

    Returns:
        A dictionary containing market statistics or None if no data available.
        Example:
        {
            "up": 450,         # 上漲家數
            "down": 350,       # 下跌家數
            "unchanged": 200,  # 平盤家數
        }
    """
    data_date_str_without_dash = data_date.isoformat().replace("-", "")
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={data_date_str_without_dash}&response=json"

    response = requests.get(url, impersonate="chrome")

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")

    data = response.json()

    if data.get("stat") == "很抱歉，沒有符合條件的資料!":
        return None

    if data.get("stat") != "OK":
        raise Exception(f"API error:\n{data}")

    print(f"Got market stats data for {data_date}")

    # Parse the market statistics from "tables" array
    # Looking for the table with title "大盤統計資訊" or parsing "fields" and "data"
    # The MI_INDEX response contains tables like:
    # - 漲跌證券數合計 (Rise/Fall stocks count)
    # Response structure:
    # {
    #     "tables": [
    #         {
    #             "title": "...",
    #             "fields": ["項目", "漲停", "上漲", "持平", "下跌", "跌停"],
    #             "data": [
    #                 ["整體市場", "65", "559", "222", "512", "24"],
    #                 ...
    #             ]
    #         }
    #     ]
    # }
    tables = data.get("tables", [])

    for table in tables:
        fields = table.get("fields", [])
        table_data = table.get("data", [])

        # Find the table with 上漲/下跌/持平 fields
        if "上漲" in fields and "下跌" in fields:
            # Find the "整體市場" row for overall market statistics
            for row in table_data:
                if len(row) >= 6 and "整體市場" in row[0]:
                    # Parse fields: [項目, 漲停, 上漲, 持平, 下跌, 跌停]
                    # Example: ["整體市場", "65", "559", "222", "512", "24"]
                    up_limit = int(row[1].replace(",", ""))  # 漲停
                    up = int(row[2].replace(",", ""))  # 上漲
                    unchanged = int(row[3].replace(",", ""))  # 持平
                    down = int(row[4].replace(",", ""))  # 下跌
                    down_limit = int(row[5].replace(",", ""))  # 跌停

                    return {
                        "up": up,
                        "up_limit": up_limit,
                        "down": down,
                        "down_limit": down_limit,
                        "unchanged": unchanged,
                    }

    raise Exception(f"Could not find market statistics in response: {data}")
