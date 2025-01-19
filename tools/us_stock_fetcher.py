import yfinance as yf
import pandas as pd
from datetime import datetime

import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz

def get_earnings_dates(ticker, start_date, end_date):
 # Fetching the stock data
 stock = yf.Ticker(ticker)

 # Getting the earnings dates
 earnings_dates = stock.earnings_dates

 # Filtering by date range
 filtered_dates = earnings_dates[(earnings_dates.index >= start_date) & (earnings_dates.index <= end_date)]

 return filtered_dates


# Define your parameters
ticker_symbol = "AAPL"  # Example: Apple Inc.
start_date = "2020-01-01"
end_date = "2023-12-31"

# Convert string dates to datetime objects
start_date_dt = pd.to_datetime(start_date)
end_date_dt = pd.to_datetime(end_date)

# Make start_date and end_date tz-aware
timezone = pytz.timezone('America/New_York')
start_date_dt = timezone.localize(start_date_dt)
end_date_dt = timezone.localize(end_date_dt)


# Get earnings dates
earnings_report_dates = get_earnings_dates(ticker_symbol, start_date_dt, end_date_dt)

# Display the results
print(earnings_report_dates)
