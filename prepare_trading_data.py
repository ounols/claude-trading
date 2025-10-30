"""
Step 1: 트레이딩 데이터 준비
Claude Code Action에 전달할 데이터를 JSON으로 준비
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Alpaca imports
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetAssetsRequest
    from alpaca.trading.enums import AssetClass
    ALPACA_AVAILABLE = True
except ImportError:
    print("⚠️ alpaca-py not installed. Install with: pip install alpaca-py")
    ALPACA_AVAILABLE = False

# Windows 환경에서 UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# .env 파일 로드
load_dotenv()


class TradingDataPreparer:
    """트레이딩 데이터 준비 클래스"""

    def __init__(self, data_path: str = "./data", signature: str = "claude-trader", use_alpaca: bool = False):
        self.data_path = Path(data_path)
        self.signature = signature
        self.position_dir = self.data_path / "agent_data" / signature / "position"
        self.position_file = self.position_dir / "position.jsonl"
        self.use_alpaca = use_alpaca

        # Alpaca 클라이언트 초기화
        self.alpaca_client = None
        if use_alpaca and ALPACA_AVAILABLE:
            api_key = os.getenv("ALPACA_API_KEY")
            api_secret = os.getenv("ALPACA_API_SECRET")
            paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"

            if api_key and api_secret:
                try:
                    self.alpaca_client = TradingClient(api_key, api_secret, paper=paper)
                    print(f"✅ Alpaca client initialized ({'Paper' if paper else 'Live'} trading)")
                except Exception as e:
                    print(f"⚠️ Failed to initialize Alpaca client: {e}")
            else:
                print("⚠️ Alpaca API credentials not found in environment")

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

    def get_alpaca_portfolio(self) -> Optional[Dict[str, float]]:
        """Alpaca에서 실제 포트폴리오 가져오기"""
        if not self.alpaca_client:
            return None

        try:
            # 계좌 정보 가져오기
            account = self.alpaca_client.get_account()

            # 포지션 가져오기
            positions = self.alpaca_client.get_all_positions()

            # 포트폴리오 딕셔너리 생성
            portfolio = {symbol: 0.0 for symbol in self.symbols}
            portfolio['CASH'] = float(account.cash)

            # Alpaca 포지션을 portfolio에 반영
            for position in positions:
                symbol = position.symbol
                if symbol in portfolio:
                    portfolio[symbol] = float(position.qty)

            print(f"📊 Alpaca Portfolio loaded:")
            print(f"   - Cash: ${portfolio['CASH']:.2f}")
            print(f"   - Buying Power: ${float(account.buying_power):.2f}")
            print(f"   - Portfolio Value: ${float(account.portfolio_value):.2f}")
            print(f"   - Positions: {len([p for p in positions if p.qty != '0'])} stocks")

            return portfolio

        except Exception as e:
            print(f"⚠️ Error fetching Alpaca portfolio: {e}")
            return None

    def get_latest_position(self) -> tuple[Dict[str, float], int, str, str]:
        """최신 포지션 조회 (datetime 기준으로 정렬)"""
        # Alpaca 모드인 경우 실제 포트폴리오 가져오기
        if self.use_alpaca and self.alpaca_client:
            portfolio = self.get_alpaca_portfolio()
            if portfolio:
                # Alpaca 포트폴리오를 반환 (ID는 -1, 날짜는 None)
                return portfolio, -1, None, None

        # 로컬 파일에서 포지션 조회
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

    def get_latest_trading_date(self) -> Optional[str]:
        """데이터에서 가장 최근 거래일 찾기"""
        merged_file = self.data_path / "merged.jsonl"
        if not merged_file.exists():
            return None

        latest_date = None
        with open(merged_file, "r") as f:
            first_line = f.readline()
            if first_line.strip():
                doc = json.loads(first_line)
                series = doc.get("Time Series (Daily)", {})
                if series:
                    dates = sorted(series.keys(), reverse=True)
                    latest_date = dates[0] if dates else None

        return latest_date

    def prepare_data(self, trading_datetime: str) -> Dict:
        """Claude Code Action에 전달할 데이터 준비"""
        # datetime에서 date 추출
        date = trading_datetime.split('T')[0] if 'T' in trading_datetime else trading_datetime.split()[0]

        print(f"📊 Preparing trading data for {trading_datetime}...")

        # 포지션 조회
        current_position, current_id, _, _ = self.get_latest_position()

        # 포지션이 없고, Alpaca 모드가 아닌 경우에만 초기화
        if not current_position:
            if self.use_alpaca:
                print("❌ No Alpaca portfolio found - please check API credentials")
                return None
            else:
                print("📝 Initializing new position...")
                self.initialize_position(trading_datetime)
                current_position, current_id, _, _ = self.get_latest_position()

        # 주가 데이터 로드 (날짜 기준)
        prices = self.get_all_prices(date)

        if not prices:
            print(f"⚠️ No price data for {date}")
            # 가장 최근 거래일 찾기
            latest_date = self.get_latest_trading_date()
            if latest_date:
                print(f"🔄 Using latest available trading date: {latest_date}")
                date = latest_date
                prices = self.get_all_prices(date)
                if not prices:
                    print(f"❌ Still no price data available")
                    return None
            else:
                print(f"❌ No trading data available in merged.jsonl")
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

    # 거래 모드 출력
    if use_alpaca:
        mode = "Paper Trading" if os.getenv("ALPACA_PAPER", "true").lower() == "true" else "Live Trading"
        print(f"💼 Mode: Alpaca {mode}")
    else:
        print(f"💼 Mode: Local Simulation")

    # 데이터 준비 (Alpaca 사용 여부 전달)
    preparer = TradingDataPreparer(use_alpaca=use_alpaca)
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

    # 현재 시간 계산 (UTC 및 동부 시간)
    from datetime import timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-5)  # EST (동절기)
    # 서머타임 간단 체크: 3월 둘째 일요일 ~ 11월 첫째 일요일은 EDT (UTC-4)
    # 정확한 계산을 위해 pytz 사용이 이상적이지만, 간단하게 월로 근사
    if 3 <= now_utc.month <= 10:  # 대략적인 서머타임 기간
        et_offset = timedelta(hours=-4)  # EDT

    now_et = now_utc + et_offset

    # 세션 판단 (cron 실행 시간 고려하여 넓은 범위)
    et_hour = now_et.hour
    et_minute = now_et.minute
    current_session = ""

    # 각 cron 실행 시간대를 기준으로 ±2시간 여유 설정
    if et_hour >= 9 and et_hour < 12:
        # 9:45 AM 실행 목표 (9:00 AM ~ 11:59 AM)
        current_session = "Market Open Session (Target: 9:45 AM ET)"
    elif et_hour >= 12 and et_hour < 15:
        # 12:30 PM 실행 목표 (12:00 PM ~ 2:59 PM)
        current_session = "Mid-Day Session (Target: 12:30 PM ET)"
    elif et_hour >= 15 and et_hour <= 16:
        # 3:30 PM 실행 목표 (3:00 PM ~ 4:00 PM, 장 마감 4:00 PM)
        current_session = "Market Close Session (Target: 3:30 PM ET)"
    elif et_hour >= 6 and et_hour < 9:
        # 프리마켓 시간대
        current_session = "Pre-Market Hours (Market opens at 9:30 AM ET)"
    else:
        current_session = "After-Hours / Outside regular trading hours"

    time_context = f"""
**Current Time**:
- UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}
- Eastern Time: {now_et.strftime('%Y-%m-%d %H:%M:%S ET')}
- Trading Session: {current_session}
"""

    with open(prompt_file, "w") as f:
        f.write(f"""You are an expert stock trader managing a NASDAQ 100 portfolio with a LONG-TERM VALUE INVESTING approach.

**INVESTMENT PHILOSOPHY**:
- This is a LONG-TERM investment strategy focused on building wealth over months/years
- Prioritize companies with strong fundamentals and sustainable competitive advantages
- Make CAUTIOUS and WELL-RESEARCHED decisions - quality over quantity
- Short-term market volatility should not trigger panic selling or hasty decisions
- Compound growth through patient investing is the ultimate goal

**Trading Session**: {trading_data['datetime']}
**Date**: {trading_data['date']}
{time_context}
**Trading Schedule Context**:
You have 3 opportunities per trading day (Mon-Fri) to analyze and make decisions:
1. **Market Open** (9:45 AM ET) - Right after market opens, assess overnight news and opening sentiment
2. **Mid-Day** (12:30 PM ET) - Mid-session check, evaluate morning trends and any breaking news
3. **Market Close** (3:30 PM ET) - Final 30 minutes, review full day's action and prepare for next session

**Decision Guidelines by Session**:
- **Morning Session**: React to overnight developments and set direction for the day
- **Mid-Day Session**: Only adjust if significant intraday developments warrant action
- **Close Session**: Reflect on the full day's data, avoid impulsive end-of-day reactions
- **Remember**: With 3 chances daily, you don't need to act every time - patience and selectivity are virtues

**Current Portfolio** (Total: ${trading_data['portfolio']['total_value']:.2f}):
- Cash: ${trading_data['portfolio']['cash']:.2f}
- Holdings: {len(trading_data['portfolio']['holdings'])} positions
{news_stats}
**Your Task**:
1. **Analyze Market News**: Review the news data carefully
   - General market sentiment and trends
   - Sector-specific developments
   - Individual stock news for holdings and potential buys
   - **IMPORTANT**: If you need more context or verification, research additional sources

2. **Conduct Additional Research** (HIGHLY ENCOURAGED):
   - Use available tools to search for more information when needed
   - Verify company fundamentals, earnings reports, and growth projections
   - Check for breaking news or developments not in the provided data
   - Look up valuations, P/E ratios, analyst ratings when considering trades
   - Be thorough - well-informed decisions are more important than quick ones

3. **Evaluate Portfolio**: Consider current positions with a long-term lens
   - Are these companies worth holding for the next 6-12 months?
   - Do they have sustainable competitive advantages?
   - Is the current allocation aligned with long-term goals?

4. **Make Trading Decisions**: Based on thorough fundamental analysis
   - Buy opportunities: Strong fundamentals + long-term growth potential + reasonable valuation
   - Sell triggers: Deteriorating fundamentals, overvaluation, or better opportunities elsewhere
   - Hold: Often the best decision - don't trade just to trade

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

**Critical Guidelines**:
- Base decisions on thorough fundamental analysis and comprehensive research
- Use additional research tools liberally - verify claims and dig deeper when needed
- Reference specific news items and research findings in your analysis
- Consider both risks and opportunities with a long-term perspective
- Maintain portfolio diversification for risk management
- Remember: It's perfectly acceptable to make NO trades if conditions aren't optimal
- Quality of decisions matters far more than quantity of trades

**Long-term Investment Mindset**:
- Ask yourself: "Would I want to hold this company for the next 1-2 years?"
- Avoid reacting to short-term noise or market sentiment swings
- Focus on sustainable business models and competitive advantages
- Patient capital beats reactive trading

Please analyze the data thoroughly, conduct additional research as needed, and provide your trading decision in JSON format only.
""")

    print(f"✅ Prompt saved to: {prompt_file}")


if __name__ == "__main__":
    main()
