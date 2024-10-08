from flask import Flask, request, jsonify
import yfinance as yf
import requests_cache
from requests import Session
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin, MemoryQueueBucket
from pyrate_limiter import Duration, RequestRate, Limiter
import pandas as pd
import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# Set up logging for error handling
logging.basicConfig(filename='nifty50_data_fetch.log', level=logging.ERROR,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Set up a cached session with dynamic rate limiting
class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    pass

initial_rate = RequestRate(2, Duration.SECOND * 5)
session = CachedLimiterSession(
    limiter=Limiter(initial_rate),
    bucket_class=MemoryQueueBucket,
    backend=SQLiteCache("yfinance.cache"),
)

# Load the list of Nifty 50 companies from the CSV file
csv_file_path = "C:/Users/santo/Downloads/ind_nifty50list.csv"  # Update this path
nifty_50_companies = pd.read_csv(csv_file_path)
tickers = nifty_50_companies['Symbol'].apply(lambda x: x + ".NS").tolist()

# Initialize the Tickers object with all Nifty 50 tickers
nifty50_tickers = yf.Tickers(' '.join(tickers), session=session)

# Directory to save the data
live_data_dir = "nifty50_live_data"
historical_data_dir = "nifty50_historical_data"
os.makedirs(live_data_dir, exist_ok=True)
os.makedirs(historical_data_dir, exist_ok=True)

def fetch_live_market_data(ticker):
    """Fetch live market data for a Nifty 50 company."""
    try:
        company = nifty50_tickers.tickers[ticker]
        live_data = {
            "current_price": company.history(period="1d", interval="1m"),
            "live_info": {
                "previous_close": company.info.get("previousClose"),
                "open": company.info.get("open"),
                "bid": company.info.get("bid"),
                "ask": company.info.get("ask"),
                "day_low": company.info.get("dayLow"),
                "day_high": company.info.get("dayHigh"),
                "volume": company.info.get("volume"),
            }
        }

        live_data_output_dir = os.path.join(live_data_dir, ticker)
        os.makedirs(live_data_output_dir, exist_ok=True)
        live_data["current_price"].to_csv(os.path.join(live_data_output_dir, f"{ticker}_live_data.csv"))

        live_info_file_path = os.path.join(live_data_output_dir, f"{ticker}_live_info.json")
        with open(live_info_file_path, 'w') as f:
            json.dump(live_data["live_info"], f)

        return {"status": "success", "message": f"Live market data for {ticker} fetched and saved."}

    except Exception as e:
        logging.error(f"Failed to fetch live data for {ticker}: {e}")
        return {"status": "error", "message": str(e)}

def fetch_historical_data(ticker):
    """Fetch historical data for a Nifty 50 company."""
    try:
        company = nifty50_tickers.tickers[ticker]
        historical_data = company.history(period="max")

        data_output_dir = os.path.join(historical_data_dir, ticker)
        os.makedirs(data_output_dir, exist_ok=True)
        historical_data.to_csv(os.path.join(data_output_dir, f"{ticker}_historical_data.csv"))

        return {"status": "success", "message": f"Historical data for {ticker} fetched and saved."}

    except Exception as e:
        logging.error(f"Failed to fetch historical data for {ticker}: {e}")
        return {"status": "error", "message": str(e)}

def fetch_data_in_parallel(tickers, fetch_function):
    """Fetch data in parallel using ThreadPoolExecutor."""
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_function, ticker) for ticker in tickers]
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logging.error(f"Error in parallel execution: {e}")
                results.append({"status": "error", "message": str(e)})
    return results

@app.route('/market-data/live', methods=['POST'])
def fetch_live_market_data_endpoint():
    tickers = request.json.get('tickers', [])
    result = fetch_data_in_parallel(tickers, fetch_live_market_data)
    return jsonify(result)

@app.route('/market-data/historical', methods=['POST'])
def fetch_historical_data_endpoint():
    tickers = request.json.get('tickers', [])
    result = fetch_data_in_parallel(tickers, fetch_historical_data)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
