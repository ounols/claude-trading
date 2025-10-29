"""
Step 1: 트레이딩 데이터 준비
Claude Code Action에 전달할 데이터를 JSON으로 준비
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class TradingDataPreparer:
    """트레이딩 데이터 준비 클래스"""

    def __init__(self, data_path: str = "./data", signature: str = "claude-trader"):
        self.data_path = Path(data_path)
        self.signature = signature
        self.position_dir = self.data_path / "agent_data" / signature / "position"
        self.position_file = self.position_dir / "position.jsonl"

        # NASDAQ 100 심볼
        self.symbols = [
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

    def initialize_position(self, init_datetime: str, initial_cash: float = 10000.0) -> None:
        """초기 포지션 생성"""
        if self.position_file.exists():
            print(f"⚠️ Position file already exists")
            return

        self.position_dir.mkdir(parents=True, exist_ok=True)

        init_position = {symbol: 0 for symbol in self.symbols}
        init_position['CASH'] = initial_cash

        # datetime과 date 분리
        init_date = init_datetime.split('T')[0] if 'T' in init_datetime else init_datetime.split()[0]

        with open(self.position_file, "w") as f:
            f.write(json.dumps({
                "datetime": init_datetime,
                "date": init_date,
                "id": 0,
                "positions": init_position
            }) + "\n")

        print(f"✅ Initialized position with ${initial_cash} at {init_datetime}")

    def get_latest_position(self) -> tuple[Dict[str, float], int, str, str]:
        """최신 포지션 조회 (datetime 기준으로 정렬)"""
        if not self.position_file.exists():
            return {}, -1, None, None

        positions = []
        with open(self.position_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                doc = json.loads(line)
                positions.append(doc)

        if not positions:
            return {}, -1, None, None

        # datetime 기준으로 정렬하여 최신 것 선택
        positions.sort(key=lambda x: x.get("datetime", x.get("date", "")))
        latest = positions[-1]

        return (
            latest.get("positions", {}),
            latest.get("id", -1),
            latest.get("date"),
            latest.get("datetime")
        )

    def get_price_data(self, symbol: str, date: str) -> Optional[Dict]:
        """로컬 데이터에서 주가 조회"""
        merged_file = self.data_path / "merged.jsonl"

        if not merged_file.exists():
            return None

        with open(merged_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                doc = json.loads(line)
                meta = doc.get("Meta Data", {})

                if meta.get("2. Symbol") != symbol:
                    continue

                series = doc.get("Time Series (Daily)", {})
                day_data = series.get(date)

                if day_data:
                    return {
                        "symbol": symbol,
                        "date": date,
                        "open": float(day_data.get("1. buy price", 0)),
                        "high": float(day_data.get("2. high", 0)),
                        "low": float(day_data.get("3. low", 0)),
                        "close": float(day_data.get("4. sell price", 0)),
                        "volume": int(day_data.get("5. volume", 0))
                    }

        return None

    def get_all_prices(self, date: str) -> Dict[str, float]:
        """모든 종목의 시가 조회"""
        prices = {}
        for symbol in self.symbols:
            data = self.get_price_data(symbol, date)
            if data:
                prices[symbol] = data["open"]
        return prices

    def load_market_news(self) -> Optional[Dict]:
        """시장 뉴스 데이터 로드"""
        news_file = Path("market_news.json")
        if not news_file.exists():
            print("⚠️ No market news file found")
            return None

        try:
            with open(news_file, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading market news: {e}")
            return None

    def prepare_data(self, trading_datetime: str) -> Dict:
        """Claude Code Action에 전달할 데이터 준비"""
        # datetime에서 date 추출
        date = trading_datetime.split('T')[0] if 'T' in trading_datetime else trading_datetime.split()[0]

        print(f"📊 Preparing trading data for {trading_datetime}...")

        # 포지션 초기화 (없는 경우)
        current_position, current_id, _, _ = self.get_latest_position()
        if not current_position:
            print("📝 Initializing new position...")
            self.initialize_position(trading_datetime)
            current_position, current_id, _, _ = self.get_latest_position()

        # 주가 데이터 로드 (날짜 기준)
        prices = self.get_all_prices(date)

        if not prices:
            print(f"⚠️ No price data for {date}")
            return None

        # 포트폴리오 가치 계산
        total_value = current_position.get("CASH", 0)
        holdings = []

        for symbol in self.symbols:
            shares = current_position.get(symbol, 0)
            if shares > 0:
                current_price = prices.get(symbol, 0)
                value = shares * current_price
                total_value += value
                holdings.append({
                    "symbol": symbol,
                    "shares": shares,
                    "price": current_price,
                    "value": value
                })

        # 시장 뉴스 로드
        market_news = self.load_market_news()

        # Claude에게 전달할 데이터 구조
        trading_data = {
            "datetime": trading_datetime,
            "date": date,
            "portfolio": {
                "total_value": total_value,
                "cash": current_position.get("CASH", 0),
                "holdings": holdings,
                "position_id": current_id
            },
            "market": {
                "prices": prices,
                "available_symbols": self.symbols
            },
            "news": market_news if market_news else {
                "market_overview": [],
                "sector_news": [],
                "top_stocks_news": {}
            },
            "metadata": {
                "signature": self.signature,
                "execution_timestamp": trading_datetime
            }
        }

        print(f"✅ Data prepared:")
        print(f"   - Portfolio value: ${total_value:.2f}")
        print(f"   - Cash: ${current_position.get('CASH', 0):.2f}")
        print(f"   - Holdings: {len(holdings)} positions")
        print(f"   - Prices: {len(prices)} stocks")
        if market_news:
            print(f"   - Market news: {len(market_news.get('market_overview', []))} overview articles")
            print(f"   - Sector news: {len(market_news.get('sector_news', []))} sector articles")
            print(f"   - Stock news: {len(market_news.get('top_stocks_news', {}))} stocks covered")

        return trading_data


def main():
    """메인 실행 함수"""
    # 거래 모드 확인
    use_alpaca = os.getenv("USE_ALPACA", "false").lower() == "true"
    simulation_mode = os.getenv("SIMULATION_MODE", "true").lower() == "true"

    # 거래 날짜 및 시간
    trading_datetime = os.getenv("TRADING_DATETIME")

    if not trading_datetime:
        # 환경변수에서 날짜만 있는 경우
        trading_date = os.getenv("TRADING_DATE")
        if trading_date:
            # Alpaca 모드에서 과거 날짜 입력 시 경고 및 무시
            if use_alpaca and not simulation_mode:
                today = datetime.now().strftime("%Y-%m-%d")
                if trading_date != today:
                    print(f"\n⚠️  WARNING: Alpaca mode cannot use past dates")
                    print(f"   Requested date: {trading_date}")
                    print(f"   Current date: {today}")
                    print(f"   → Ignoring past date and using today's date")
                    print(f"   → For backtesting, use SIMULATION_MODE=true\n")
                    trading_date = today

            # 날짜만 있으면 현재 시간 추가
            now = datetime.now()
            trading_datetime = f"{trading_date}T{now.strftime('%H:%M:%S')}"
        else:
            # 둘 다 없으면 현재 날짜+시간
            now = datetime.now()
            if now.weekday() >= 5:  # 주말
                print("⚠️ Weekend - No trading")
                return
            trading_datetime = now.strftime("%Y-%m-%dT%H:%M:%S")

    print(f"📅 Trading DateTime: {trading_datetime}")

    # 데이터 준비
    preparer = TradingDataPreparer()
    trading_data = preparer.prepare_data(trading_datetime)

    if not trading_data:
        print("❌ Failed to prepare data")
        return

    # JSON 파일로 저장 (Claude Code Action이 읽을 수 있도록)
    output_file = Path("trading_data.json")
    with open(output_file, "w") as f:
        json.dump(trading_data, f, indent=2)

    print(f"\n✅ Trading data saved to: {output_file}")

    # 프롬프트도 준비
    prompt_file = Path("trading_prompt.txt")

    # 뉴스 통계 계산
    news_stats = ""
    if trading_data.get('news'):
        news = trading_data['news']
        market_count = len(news.get('market_overview', []))
        sector_count = len(news.get('sector_news', []))
        stock_count = len(news.get('top_stocks_news', {}))
        news_stats = f"""
**Market Intelligence Available**:
- {market_count} general market news articles
- {sector_count} sector-specific news articles
- {stock_count} individual stock news items

Please carefully review the news data in trading_data.json before making decisions.
"""

    with open(prompt_file, "w") as f:
        f.write(f"""You are an expert stock trader managing a NASDAQ 100 portfolio.

**Trading Session**: {trading_data['datetime']}
**Date**: {trading_data['date']}

**Current Portfolio** (Total: ${trading_data['portfolio']['total_value']:.2f}):
- Cash: ${trading_data['portfolio']['cash']:.2f}
- Holdings: {len(trading_data['portfolio']['holdings'])} positions
{news_stats}
**Your Task**:
1. **Analyze Market News**: Review the news data carefully
   - General market sentiment and trends
   - Sector-specific developments
   - Individual stock news for holdings and potential buys

2. **Evaluate Portfolio**: Consider current positions against market conditions

3. **Make Trading Decisions**: Based on fundamental analysis
   - Buy opportunities: Strong fundamentals + positive news
   - Sell triggers: Negative news, overvaluation, or risk management
   - Hold: When no clear action is warranted

**Data Available**:
- `trading_data.json` contains:
  - Portfolio positions and cash
  - Current stock prices for all NASDAQ 100 stocks
  - Market news (general, sector, and stock-specific)

**Output Format** (MUST be valid JSON):
{{
  "analysis": "Your detailed market and news analysis with specific references to news items",
  "actions": [
    {{"action": "buy", "symbol": "AAPL", "amount": 10, "reason": "Strong earnings report"}},
    {{"action": "sell", "symbol": "MSFT", "amount": 5, "reason": "Regulatory concerns"}}
  ]
}}

If no trades needed:
{{
  "analysis": "Reason for holding based on news and market analysis",
  "actions": []
}}

**Important**:
- Base decisions on news content and fundamental analysis
- Reference specific news items in your analysis
- Consider both risks and opportunities
- Maintain portfolio diversification

Please analyze the data and provide your trading decision in JSON format only.
""")

    print(f"✅ Prompt saved to: {prompt_file}")


if __name__ == "__main__":
    main()
