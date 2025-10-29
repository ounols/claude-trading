"""
Claude Code 기반 자동 트레이딩 시스템
GitHub Actions에서 매일 실행 가능한 단순화된 버전
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import anthropic

# 환경 변수에서 API 키 로드
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")


class ClaudeTrader:
    """Claude API를 사용한 자동 트레이딩 에이전트"""

    def __init__(
        self,
        signature: str = "claude-trader",
        initial_cash: float = 10000.0,
        data_path: str = "./data"
    ):
        self.signature = signature
        self.initial_cash = initial_cash
        self.data_path = Path(data_path)
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # 포지션 파일 경로
        self.position_dir = self.data_path / "agent_data" / signature / "position"
        self.position_file = self.position_dir / "position.jsonl"
        self.position_dir.mkdir(parents=True, exist_ok=True)

        # 로그 디렉토리
        self.log_dir = self.data_path / "agent_data" / signature / "log"
        self.log_dir.mkdir(parents=True, exist_ok=True)

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

    def initialize_position(self, init_date: str) -> None:
        """초기 포지션 생성"""
        if self.position_file.exists():
            print(f"⚠️ Position file already exists: {self.position_file}")
            return

        init_position = {symbol: 0 for symbol in self.symbols}
        init_position['CASH'] = self.initial_cash

        with open(self.position_file, "w") as f:
            f.write(json.dumps({
                "date": init_date,
                "id": 0,
                "positions": init_position
            }) + "\n")

        print(f"✅ Initialized position with ${self.initial_cash}")

    def get_latest_position(self) -> tuple[Dict[str, float], int, str]:
        """최신 포지션 조회"""
        if not self.position_file.exists():
            return {}, -1, None

        latest_position = {}
        latest_id = -1
        latest_date = None

        with open(self.position_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                doc = json.loads(line)
                latest_position = doc.get("positions", {})
                latest_id = doc.get("id", -1)
                latest_date = doc.get("date")

        return latest_position, latest_id, latest_date

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

    def execute_trade(
        self,
        action: str,
        symbol: str,
        amount: int,
        price: float,
        current_position: Dict[str, float],
        current_id: int,
        date: str
    ) -> tuple[bool, Dict[str, float], str]:
        """거래 실행"""
        new_position = current_position.copy()

        if action == "buy":
            required_cash = price * amount
            if new_position.get("CASH", 0) < required_cash:
                return False, current_position, f"Insufficient cash: need ${required_cash:.2f}, have ${new_position.get('CASH', 0):.2f}"

            new_position["CASH"] -= required_cash
            new_position[symbol] = new_position.get(symbol, 0) + amount

        elif action == "sell":
            if new_position.get(symbol, 0) < amount:
                return False, current_position, f"Insufficient shares: need {amount}, have {new_position.get(symbol, 0)}"

            new_position[symbol] -= amount
            new_position["CASH"] = new_position.get("CASH", 0) + (price * amount)

        else:
            return False, current_position, f"Invalid action: {action}"

        # 포지션 저장
        with open(self.position_file, "a") as f:
            f.write(json.dumps({
                "date": date,
                "id": current_id + 1,
                "this_action": {
                    "action": action,
                    "symbol": symbol,
                    "amount": amount
                },
                "positions": new_position
            }) + "\n")

        return True, new_position, f"Success: {action} {amount} shares of {symbol} at ${price:.2f}"

    def build_prompt(self, date: str, current_position: Dict, prices: Dict) -> str:
        """트레이딩 프롬프트 생성"""
        # 포트폴리오 가치 계산
        total_value = current_position.get("CASH", 0)
        holdings_info = []

        for symbol in self.symbols:
            shares = current_position.get(symbol, 0)
            if shares > 0:
                current_price = prices.get(symbol, 0)
                value = shares * current_price
                total_value += value
                holdings_info.append(f"  - {symbol}: {shares} shares @ ${current_price:.2f} = ${value:.2f}")

        holdings_text = "\n".join(holdings_info) if holdings_info else "  (No holdings)"

        prompt = f"""You are an expert stock trader managing a portfolio of NASDAQ 100 stocks.

**Today's Date**: {date}

**Current Portfolio** (Total Value: ${total_value:.2f}):
{holdings_text}
  - CASH: ${current_position.get('CASH', 0):.2f}

**Today's Opening Prices** (Sample - top 20):
"""
        # 가격 정보 추가 (상위 20개만)
        price_items = list(prices.items())[:20]
        for symbol, price in price_items:
            prompt += f"  - {symbol}: ${price:.2f}\n"

        prompt += f"""
**Your Task**:
Analyze the current market conditions and your portfolio, then decide on trading actions.

**Available Actions**:
1. BUY <SYMBOL> <AMOUNT> - Buy shares
2. SELL <SYMBOL> <AMOUNT> - Sell shares
3. HOLD - No trades today

**Response Format**:
You MUST respond with a JSON object containing your decision:

{{
  "analysis": "Brief analysis of market conditions and reasoning",
  "actions": [
    {{"action": "buy", "symbol": "AAPL", "amount": 10}},
    {{"action": "sell", "symbol": "MSFT", "amount": 5}}
  ]
}}

If you don't want to trade, use:
{{
  "analysis": "Reason for holding",
  "actions": []
}}

**Important**:
- Only trade with available cash
- Only sell shares you own
- Consider diversification
- Response must be valid JSON only, no additional text
"""

        return prompt

    async def get_trading_decision(self, date: str, current_position: Dict, prices: Dict) -> Dict:
        """Claude에게 트레이딩 결정 요청"""
        prompt = self.build_prompt(date, current_position, prices)

        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            response_text = message.content[0].text

            # JSON 파싱
            # Claude가 ```json으로 감싸서 보낼 수 있으므로 처리
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            decision = json.loads(response_text)
            return decision

        except Exception as e:
            print(f"❌ Error getting Claude decision: {e}")
            return {"analysis": "Error occurred", "actions": []}

    async def run_trading_day(self, date: str) -> None:
        """하루 트레이딩 세션 실행"""
        print(f"\n{'='*60}")
        print(f"📅 Trading Day: {date}")
        print(f"{'='*60}")

        # 1. 현재 포지션 조회
        current_position, current_id, _ = self.get_latest_position()

        if not current_position:
            print("⚠️ No position found, initializing...")
            self.initialize_position(date)
            current_position, current_id, _ = self.get_latest_position()

        # 2. 오늘 주가 조회
        prices = self.get_all_prices(date)

        if not prices:
            print(f"⚠️ No price data available for {date}")
            return

        print(f"📊 Loaded prices for {len(prices)} stocks")

        # 3. Claude에게 결정 요청
        print("🤖 Requesting trading decision from Claude...")
        decision = await self.get_trading_decision(date, current_position, prices)

        print(f"\n💡 Analysis: {decision.get('analysis', 'N/A')}")

        # 4. 거래 실행
        actions = decision.get("actions", [])

        if not actions:
            print("📊 No trades today (HOLD)")
            # 거래 없음 기록
            with open(self.position_file, "a") as f:
                f.write(json.dumps({
                    "date": date,
                    "id": current_id + 1,
                    "this_action": {"action": "no_trade", "symbol": "", "amount": 0},
                    "positions": current_position
                }) + "\n")
        else:
            print(f"\n📈 Executing {len(actions)} trades:")

            for i, trade in enumerate(actions, 1):
                action = trade.get("action", "").lower()
                symbol = trade.get("symbol", "").upper()
                amount = trade.get("amount", 0)

                if symbol not in prices:
                    print(f"  {i}. ❌ Skip: {symbol} - No price data")
                    continue

                price = prices[symbol]
                success, new_position, message = self.execute_trade(
                    action, symbol, amount, price, current_position, current_id + i - 1, date
                )

                if success:
                    print(f"  {i}. ✅ {action.upper()} {amount} {symbol} @ ${price:.2f}")
                    current_position = new_position
                else:
                    print(f"  {i}. ❌ {action.upper()} {amount} {symbol} - {message}")

        # 5. 최종 포트폴리오 출력
        total_value = current_position.get("CASH", 0)
        for symbol in self.symbols:
            shares = current_position.get(symbol, 0)
            if shares > 0 and symbol in prices:
                total_value += shares * prices[symbol]

        print(f"\n💰 End of Day Portfolio Value: ${total_value:.2f}")
        print(f"   Cash: ${current_position.get('CASH', 0):.2f}")

        # 로그 저장
        log_file = self.log_dir / date / "log.json"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        with open(log_file, "w") as f:
            json.dumps({
                "date": date,
                "decision": decision,
                "final_value": total_value
            }, f, indent=2)


async def main():
    """메인 실행 함수"""
    # 오늘 날짜 (또는 지정된 날짜)
    today = os.getenv("TRADING_DATE")

    if not today:
        # 평일만 거래
        now = datetime.now()
        if now.weekday() >= 5:  # 주말
            print("⚠️ Weekend - No trading")
            return
        today = now.strftime("%Y-%m-%d")

    print(f"🚀 Claude Trader Starting...")
    print(f"📅 Trading Date: {today}")

    trader = ClaudeTrader()
    await trader.run_trading_day(today)

    print(f"\n✅ Trading session completed!")


if __name__ == "__main__":
    asyncio.run(main())
