"""
주가 데이터 수집 스크립트
무료 API (yfinance)와 웹 스크래핑을 사용하여 데이터 수집
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import time

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    print("⚠️ yfinance not installed. Install with: pip install yfinance")
    YFINANCE_AVAILABLE = False


NASDAQ_100_SYMBOLS = [
    "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
    "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
    "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
    "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
    "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
    "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
    "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
    "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
    "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
    "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
    "ON", "BIIB", "LULU", "CDW", "GFS"
]


def fetch_stock_data_yfinance(symbol: str, start_date: str, end_date: str) -> Optional[Dict]:
    """yfinance를 사용하여 주가 데이터 가져오기"""
    if not YFINANCE_AVAILABLE:
        return None

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)

        if df.empty:
            print(f"  ⚠️ No data for {symbol}")
            return None

        # Alpha Vantage 형식으로 변환
        time_series = {}

        for date, row in df.iterrows():
            date_str = date.strftime("%Y-%m-%d")
            time_series[date_str] = {
                "1. buy price": str(row["Open"]),
                "2. high": str(row["High"]),
                "3. low": str(row["Low"]),
                "4. sell price": str(row["Close"]),
                "5. volume": str(int(row["Volume"]))
            }

        result = {
            "Meta Data": {
                "1. Information": "Daily Prices",
                "2. Symbol": symbol,
                "3. Last Refreshed": end_date,
                "4. Output Size": "Compact",
                "5. Time Zone": "US/Eastern"
            },
            "Time Series (Daily)": time_series
        }

        return result

    except Exception as e:
        print(f"  ❌ Error fetching {symbol}: {e}")
        return None


def update_merged_file(data: Dict, merged_path: Path) -> None:
    """merged.jsonl 파일 업데이트"""
    symbol = data["Meta Data"]["2. Symbol"]

    # 기존 데이터 로드
    existing_data = {}
    if merged_path.exists():
        with open(merged_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                doc = json.loads(line)
                sym = doc["Meta Data"]["2. Symbol"]
                existing_data[sym] = doc

    # 새 데이터와 병합
    if symbol in existing_data:
        # 기존 시계열 데이터와 병합
        existing_series = existing_data[symbol]["Time Series (Daily)"]
        new_series = data["Time Series (Daily)"]
        existing_series.update(new_series)
        existing_data[symbol]["Time Series (Daily)"] = existing_series
        existing_data[symbol]["Meta Data"]["3. Last Refreshed"] = data["Meta Data"]["3. Last Refreshed"]
    else:
        existing_data[symbol] = data

    # 파일에 쓰기
    with open(merged_path, "w") as f:
        for sym in sorted(existing_data.keys()):
            f.write(json.dumps(existing_data[sym]) + "\n")


def fetch_all_stocks(
    symbols: List[str],
    start_date: str,
    end_date: str,
    output_dir: Path
) -> None:
    """모든 종목 데이터 수집"""
    output_dir.mkdir(parents=True, exist_ok=True)
    merged_path = output_dir / "merged.jsonl"

    print(f"📊 Fetching stock data from {start_date} to {end_date}")
    print(f"📂 Output directory: {output_dir}")

    success_count = 0
    failed_count = 0

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Fetching {symbol}...", end=" ")

        # yfinance로 데이터 가져오기
        data = fetch_stock_data_yfinance(symbol, start_date, end_date)

        if data:
            # 개별 파일 저장
            individual_file = output_dir / f"daily_prices_{symbol}.json"
            with open(individual_file, "w") as f:
                json.dump(data, f, indent=2)

            # merged 파일 업데이트
            update_merged_file(data, merged_path)

            print("✅")
            success_count += 1
        else:
            print("❌")
            failed_count += 1

        # API 제한 방지를 위한 지연
        time.sleep(0.1)

    print(f"\n✅ Success: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📁 Data saved to: {merged_path}")


def get_latest_trading_date() -> str:
    """최신 거래일 구하기 (오늘 또는 가장 최근 평일)"""
    now = datetime.now()

    # 주말이면 금요일로
    while now.weekday() >= 5:
        now -= timedelta(days=1)

    return now.strftime("%Y-%m-%d")


def main():
    """메인 실행 함수"""
    # 환경 변수에서 날짜 범위 가져오기
    end_date = os.getenv("END_DATE", get_latest_trading_date())
    days_back = int(os.getenv("DAYS_BACK", "30"))

    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
    start_date_obj = end_date_obj - timedelta(days=days_back)
    start_date = start_date_obj.strftime("%Y-%m-%d")

    # 출력 디렉토리
    data_dir = Path(os.getenv("DATA_DIR", "./data"))

    print("🚀 Stock Data Fetcher")
    print("=" * 60)
    print(f"📅 Date range: {start_date} to {end_date}")
    print(f"📊 Symbols: {len(NASDAQ_100_SYMBOLS)} stocks")
    print("=" * 60)

    if not YFINANCE_AVAILABLE:
        print("\n❌ yfinance is not installed!")
        print("Install it with: pip install yfinance")
        return

    fetch_all_stocks(NASDAQ_100_SYMBOLS, start_date, end_date, data_dir)

    print("\n✅ Data fetch completed!")


if __name__ == "__main__":
    main()
