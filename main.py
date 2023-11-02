#!/usr/bin/python3
import time
import requests
import validators
from datetime import datetime, timezone

from settings import check_interval, max_ping
from postgres import Postgresql


def epoch_to_timestamp_tz(epoch: int):
    """
    Function to convert epoch to timestamp with timezone
    :param epoch: either epoch seconds or epoch milliseconds
    """
    if epoch > 100000000000:
        # Assuming epoch milliseconds
        epoch /= 1000
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt


def check(website: dict):
    """
    This is the main checking function
    :param website: The website/proxy object
    :return: the result in the form of a dict
    """
    test_url = website['url'] + website['test_path']
    if validators.url(website['test_path']):
        print(f"Testing {website['url']} -> {website['test_path']} ... ", end="")
        test_url = website['test_path']
    else:
        print(f"Testing {website['url'] + website['test_path']} ... ", end="")

    result = {
        "up": False,
        "ping": None,
        "return_code": 0,
        "test_reason": None
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }

    start_time = time.time()
    try:
        response = requests.get(test_url, timeout=max_ping, headers=headers)
        end_time = time.time()
        result["ping"] = end_time - start_time
        result["return_code"] = response.status_code
        if result["return_code"] >= 300 or 200 > result["return_code"]:
            result["test_reason"] = f"Return code not satisfied: {result['return_code']}"
        elif website["test_match"] in response.text:
            result["up"] = True
        else:
            result["test_reason"] = "Test match not found"
    except requests.exceptions.Timeout:
        result["test_reason"] = f"Timeout {max_ping}s"
    except Exception as e:
        result["test_reason"] = str(e)

    if result["ping"] is None:
        end_time = time.time()
        result["ping"] = end_time - start_time
    if result["ping"] > max_ping:
        result["up"] = False

    return result


if __name__ == '__main__':

    # Checking if PostgreSQL is running
    psql = Postgresql()
    if not psql.up:
        exit(1)

    while True:
        websites = []
        websites_psql = psql.get_all("website", "id")
        proxies_psql = psql.get_all("proxy_list", "id")
        print()
        for website_psql in websites_psql:
            website = website_psql._asdict()
            website["proxies"] = []
            for proxy_psql in proxies_psql:
                proxy = proxy_psql._asdict()
                if website["id"] == proxy["web_id"]:
                    if proxy["test_match"] is None:
                        proxy["test_match"] = website["test_match"]
                    if proxy["test_path"] is None:
                        proxy["test_path"] = website["test_path"]
                    website["proxies"].append(proxy)
            websites.append(website)
        """
        After this, the "websites" now looks like this kind of:
        {
            "added_time": "2023-07-14 16:39:14.800135+02:00",
            "description": "blah bllahblhalbhalbhalblahblablh",
            "id": 3,
            "last_active": "1970-01-01 01:00:00+01:00",
            "last_checked": "1970-01-01 01:00:00+01:00",
            "name": "Website Name",
            "ping": 0.35,
            "return_code": 200,
            "test_match": "/static/main.js",
            "test_path": "https://apibay.org/q.php?q=pcnt:recent",
            "test_reason": null,
            "up": true,
            "url": "https://example.com",
            "proxies": [
                {
                    "id": 2,
                    "web_id": 3,
                    "added_time": "2023-07-15 12:28:35.474263+02:00",
                    "last_active": "1970-01-01 01:00:00+01:00",
                    "last_checked": "1970-01-01 01:00:00+01:00",
                    "official": false,
                    "ping": 1.51,
                    "return_code": 200,
                    "test_match": "<a href=\"magnet:?xt=urn:btih:",
                    "test_path": "/recent",
                    "test_reason": null,
                    "up": true,
                    "url": "https://test.ru"
                },
                {
                    ...
                },
                ...
            ]
        }
        """

        def print_result(r):
            if r["test_reason"] is not None:
                print(r["test_reason"])
            elif not r["up"]:
                print("FAILED")
            elif r["up"]:
                print("OK")


        # Now start the checking
        for website in websites:
            result = check(website)
            print_result(result)
            query = {
                "table": "website",
                "row": {
                    "ping": result["ping"],
                    "return_code": result["return_code"],
                    "up": result["up"],
                    "test_reason": result["test_reason"]
                },
                "where": {
                    "id": website["id"]
                }
            }
            if result["up"]:
                query["row"]["last_active"] = epoch_to_timestamp_tz(int(datetime.now().strftime('%s')))
            psql.update(query)
            for proxy in website["proxies"]:
                result = check(proxy)
                print_result(result)
                query = {
                    "table": "proxy_list",
                    "row": {
                        "ping": result["ping"],
                        "return_code": result["return_code"],
                        "up": result["up"],
                        "test_reason": result["test_reason"]
                    },
                    "where": {
                        "id": proxy["id"]
                    }
                }
                if result["up"]:
                    query["row"]["last_active"] = epoch_to_timestamp_tz(int(datetime.now().strftime('%s')))
                psql.update(query)

        # Update the last_checked for everything
        query = {
            "table": "website",
            "row": {
                "last_checked": epoch_to_timestamp_tz(int(datetime.now().strftime('%s')))
            }
        }
        psql.update(query, True)

        # Update the materialized views
        psql.refresh_view(["front_page", "website_info"])

        print("Shh! The script is sleeping")
        time.sleep(check_interval)
