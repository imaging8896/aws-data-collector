from datetime import date
from decimal import Decimal

from curl_cffi import requests


def get_investor(data_date: date):
    data_date_str_without_dash = data_date.isoformat().replace("-", "")
    url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={data_date_str_without_dash}&response=json"

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

    # [
    #     ["自營商(自行買賣)","8,786,549,833","4,521,850,637","4,264,699,196"],
    #     ["自營商(避險)","34,627,614,757","28,142,975,996","6,484,638,761"],
    #     ["投信","25,918,656,427","26,229,667,110","-311,010,683"],
    #     ["外資及陸資(不含外資自營商)","252,532,186,663","260,175,659,827","-7,643,473,164"],
    #     ["外資自營商","0","0","0"],
    #     ["合計","321,865,007,680","319,070,153,570","2,794,854,110"]
    # ]
    # "自營商表示證券自營商專戶。"
    # "投信表示本國投資信託基金。"
    # "外資及陸資表示依「華僑及外國人投資證券管理辦法」及「大陸地區投資人來臺從事證券投資及期貨交易管理辦法」辦理登記等投資人。"
    # "因外資自營商買賣金額已計入自營商買賣金額，故不納入三大法人買賣金額之合計數計算。"
    # "本統計資訊含一般、零股、盤後定價、鉅額，不含拍賣、標購。"
    # "本資訊以當日原始成交情形統計，不以證券商申報錯帳、更正帳號等調整後資料統計。"
    # "外幣成交值係以本公司當日下午3時30分公告匯率換算後加入成交金額。<br>公告匯率請參考本公司首頁>產品與服務>交易系統>雙幣ETF專區>代號對應及每日公告匯率。
    return {
        name.replace("及陸資(不含外資自營商)", ""): {
            "buy": Decimal(buy.replace(",", "")),
            "sell": Decimal(sell.replace(",", "")),
        }
        for name, buy, sell, _ in data["data"]
        if name not in ["合計", "外資自營商"]
    }
