import logging
import random

from cloudscraper import CloudScraper
from curl_cffi import requests as curl_requests


logger = logging.getLogger(__name__)


def request_get_news(url: str, mobile: bool = True, desktop: bool = True, **request_kw):
    response = None
    exception = None
    
    try:
        response = _request_get_news(url, mobile=mobile, desktop=desktop, **request_kw)
    except (curl_requests.exceptions.SSLError, curl_requests.exceptions.ConnectionError) as e:
        logger.warning(f"Request error with random client header", exc_info=True)
        exception = e

    if mobile and desktop:
        try:
            if response is None or response.status_code == 403:
                response = _request_get_news(url, mobile=False, **request_kw)
        except (curl_requests.exceptions.SSLError, curl_requests.exceptions.ConnectionError) as e:
            logger.warning(f"Request error with desktop client header", exc_info=True)
            exception = e

        try:
            if response is None or response.status_code == 403:
                response = _request_get_news(url, desktop=False, **request_kw)
        except (curl_requests.exceptions.SSLError, curl_requests.exceptions.ConnectionError) as e:
            logger.warning(f"Request error with mobile client header", exc_info=True)
            exception = e

    if response is not None:
        if response.status_code == 404:
            return "", url
        if not response.ok:
            raise curl_requests.exceptions.HTTPError(f"HTTP error {response.status_code} for url: {url}", response=response) from exception
        return response.text, response.url

    if exception is not None:
        raise exception from None
    raise RuntimeError("Code should not reach here. Response is None.")


def _request_get_news(url: str, mobile: bool = True, desktop: bool = True, impersonate: str="chrome", **request_kw):
    request_kw["impersonate"] = impersonate

    if not mobile:
        platforms = ['linux', 'windows', 'darwin']

        scraper = CloudScraper(browser={"mobile": False, "platform": random.SystemRandom().choice(platforms)})
    elif not desktop:
        scraper = CloudScraper(browser={"dessktop": False, "browser": "chrome"})
    else:
        scraper = CloudScraper()

    headers = {
        'User-Agent': scraper.headers['User-Agent'], 
        'Accept': 'application/json, text/plain, */*', 
        'Accept-Language': 'en-US,en;q=0.9', 
        # 'Referer': 'https://www.moneydj.com/XQMBondPo/api/Data/GetProdHist',
        # 'Origin': 'https://www.moneydj.com',
        'Referer': url.split('?')[0],  # Extract base URL from full URL
        'Origin': '/'.join(url.split('/')[:3]),  # Extract scheme://hostname from URL
    }

    return curl_requests.get(url, headers=headers, **request_kw)
