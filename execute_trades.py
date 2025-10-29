"""
Step 3: 거래 실행
Claude Code Action의 결정을 받아서 실제 거래를 실행
- SIMULATION_MODE=true: 시뮬레이션만 (기본)
- SIMULATION_MODE=false + Alpaca API: 실제 거래 실행
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# Alpaca 통합 (선택적)
try:
    from alpaca_trader import AlpacaTrader
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("⚠️ alpaca_trader module not available. Running in simulation mode only.")


class TradeExecutor:
    """거래 실행 클래스"""

    def __init__(
        self,
        data_path: str = "./data",
        signature: str = "claude-trader",
        simulation_mode: bool = True,
        use_alpaca: bool = False
    ):
        self.data_path = Path(data_path)
        self.signature = signature
        self.position_dir = self.data_path / "agent_data" / signature / "position"
        self.position_file = self.position_dir / "position.jsonl"
        self.log_dir = self.data_path / "agent_data" / signature / "log"

        # 거래 모드 설정
        self.simulation_mode = simulation_mode
        self.use_alpaca = use_alpaca and ALPACA_AVAILABLE and not simulation_mode

        # Alpaca 클라이언트 초기화
        self.alpaca_trader = None
        if self.use_alpaca:
            try:
                # Paper trading 사용 (안전)
                paper_trading = os.getenv("ALPACA_PAPER", "true").lower() == "true"
                self.alpaca_trader = AlpacaTrader(paper=paper_trading)
                print(f"🎯 Trading Mode: Alpaca {'Paper' if paper_trading else 'LIVE'}")
            except Exception as e:
                print(f"❌ Failed to initialize Alpaca: {e}")
                print("   Falling back to simulation mode")
                self.use_alpaca = False
        else:
            print("🎯 Trading Mode: Simulation")

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

    def get_price(self, symbol: str, date: str) -> Optional[float]:
        """특정 종목의 시가 조회"""
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
                    return float(day_data.get("1. buy price", 0))

        return None

    def execute_trade(
        self,
        action: str,
        symbol: str,
        amount: int,
        price: float,
        current_position: Dict[str, float],
        current_id: int,
        trading_datetime: str
    ) -> tuple[bool, Dict[str, float], str, Optional[float]]:
        """
        단일 거래 실행

        Args:
            price: 과거 데이터 가격 (참고용, 분석용)

        Returns:
            (성공여부, 새_포지션, 메시지, 실제_체결가)
        """
        actual_price = price  # 시뮬레이션: 과거 데이터 가격 사용
        reference_price = price  # 과거 데이터 가격 (참고용)

        # Alpaca 실제 거래
        if self.use_alpaca and self.alpaca_trader:
            success, filled_price, message = self._execute_alpaca_trade(action, symbol, amount)

            if not success:
                return False, current_position, message, None

            actual_price = filled_price

            # 가격 차이 (슬리피지) 로그
            price_diff = actual_price - reference_price
            price_diff_pct = (price_diff / reference_price) * 100 if reference_price > 0 else 0
            print(f"     📊 Price: Reference ${reference_price:.2f} → Actual ${actual_price:.2f} ({price_diff_pct:+.2f}%)")

        # 포지션 업데이트 (시뮬레이션 & Alpaca 모두)
        new_position = current_position.copy()

        if action == "buy":
            required_cash = actual_price * amount
            if new_position.get("CASH", 0) < required_cash:
                return False, current_position, f"Insufficient cash: need ${required_cash:.2f}, have ${new_position.get('CASH', 0):.2f}", None

            new_position["CASH"] -= required_cash
            new_position[symbol] = new_position.get(symbol, 0) + amount

        elif action == "sell":
            if new_position.get(symbol, 0) < amount:
                return False, current_position, f"Insufficient shares: need {amount}, have {new_position.get(symbol, 0)}", None

            new_position[symbol] -= amount
            new_position["CASH"] = new_position.get("CASH", 0) + (actual_price * amount)

        else:
            return False, current_position, f"Invalid action: {action}", None

        # datetime에서 date 추출
        date = trading_datetime.split('T')[0] if 'T' in trading_datetime else trading_datetime.split()[0]

        # 포지션 저장
        action_data = {
            "action": action,
            "symbol": symbol,
            "amount": amount,
            "price": actual_price,
            "mode": "alpaca" if self.use_alpaca else "simulation"
        }

        # Alpaca 모드일 때는 reference_price도 기록
        if self.use_alpaca and reference_price != actual_price:
            action_data["reference_price"] = reference_price
            action_data["slippage"] = actual_price - reference_price
            action_data["slippage_pct"] = ((actual_price - reference_price) / reference_price * 100) if reference_price > 0 else 0

        with open(self.position_file, "a") as f:
            f.write(json.dumps({
                "datetime": trading_datetime,
                "date": date,
                "id": current_id + 1,
                "this_action": action_data,
                "positions": new_position
            }) + "\n")

        mode_indicator = "🔴" if self.use_alpaca else "🔵"
        return True, new_position, f"{mode_indicator} {action} {amount} shares of {symbol} at ${actual_price:.2f}", actual_price

    def _execute_alpaca_trade(self, action: str, symbol: str, amount: int) -> Tuple[bool, Optional[float], str]:
        """Alpaca를 통한 실제 거래 실행"""
        if action == "buy":
            return self.alpaca_trader.execute_buy(symbol, amount)
        elif action == "sell":
            return self.alpaca_trader.execute_sell(symbol, amount)
        else:
            return False, None, f"Invalid action: {action}"

    def execute_decision(self, decision_file: str, trading_data_file: str) -> None:
        """Claude의 결정을 실행"""
        # Claude 결정 로드
        try:
            with open(decision_file, "r") as f:
                decision = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load decision file: {e}")
            return

        # 트레이딩 데이터 로드
        try:
            with open(trading_data_file, "r") as f:
                trading_data = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load trading data: {e}")
            return

        trading_datetime = trading_data.get("datetime")
        date = trading_data.get("date")
        print(f"\n📅 Executing trades for {trading_datetime}")

        # 현재 포지션
        current_position, current_id, _, _ = self.get_latest_position()

        # Claude 분석 출력
        analysis = decision.get("analysis", "No analysis provided")
        print(f"\n💡 Claude's Analysis:")
        print(f"   {analysis}")

        # 거래 실행
        actions = decision.get("actions", [])

        if not actions:
            print("\n📊 No trades (HOLD)")
            # 거래 없음 기록
            with open(self.position_file, "a") as f:
                f.write(json.dumps({
                    "datetime": trading_datetime,
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

                # 가격 조회
                price = self.get_price(symbol, date)

                if price is None:
                    print(f"  {i}. ❌ Skip: {symbol} - No price data")
                    continue

                # 거래 실행
                success, new_position, message, actual_price = self.execute_trade(
                    action, symbol, amount, price, current_position, current_id + i - 1, trading_datetime
                )

                if success:
                    price_str = f"${actual_price:.2f}" if actual_price else f"${price:.2f}"
                    print(f"  {i}. ✅ {message}")
                    current_position = new_position
                else:
                    print(f"  {i}. ❌ {action.upper()} {amount} {symbol} - {message}")

        # 최종 포트폴리오 가치 계산
        total_value = current_position.get("CASH", 0)

        for symbol in self.symbols:
            shares = current_position.get(symbol, 0)
            if shares > 0:
                price = self.get_price(symbol, date)
                if price:
                    total_value += shares * price

        print(f"\n💰 End of Session Portfolio Value: ${total_value:.2f}")
        print(f"   Cash: ${current_position.get('CASH', 0):.2f}")

        # 로그 저장 (시간 단위로 디렉토리 생성)
        # datetime을 파일명으로 사용 (콜론 제거)
        safe_datetime = trading_datetime.replace(':', '-').replace(' ', '_')
        log_file = self.log_dir / date / f"trading_log_{safe_datetime}.json"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        with open(log_file, "w") as f:
            json.dump({
                "datetime": trading_datetime,
                "date": date,
                "decision": decision,
                "final_value": total_value,
                "final_position": current_position
            }, f, indent=2)

        print(f"\n✅ Log saved to: {log_file}")


def main():
    """메인 실행 함수"""
    # 입력 파일
    decision_file = os.getenv("DECISION_FILE", "claude_decision.json")
    trading_data_file = os.getenv("TRADING_DATA_FILE", "trading_data.json")

    if not Path(decision_file).exists():
        print(f"❌ Decision file not found: {decision_file}")
        print("This file should be created by Claude Code Action")
        sys.exit(1)

    if not Path(trading_data_file).exists():
        print(f"❌ Trading data file not found: {trading_data_file}")
        sys.exit(1)

    # 거래 모드 설정
    simulation_mode = os.getenv("SIMULATION_MODE", "true").lower() == "true"
    use_alpaca = os.getenv("USE_ALPACA", "false").lower() == "true"

    print("🚀 Trade Executor Starting...")
    print(f"   Simulation Mode: {simulation_mode}")
    print(f"   Use Alpaca: {use_alpaca}")

    # Alpaca 모드에서 날짜 검증
    if not simulation_mode and use_alpaca:
        try:
            with open(trading_data_file, "r") as f:
                trading_data = json.load(f)

            trading_date = trading_data.get("date")
            today = datetime.now().strftime("%Y-%m-%d")

            if trading_date and trading_date != today:
                print(f"\n⚠️  WARNING: Alpaca mode cannot trade on past dates")
                print(f"   Requested date: {trading_date}")
                print(f"   Current date: {today}")
                print(f"   → Ignoring past date request. Alpaca trades only execute at current market prices.")
                print(f"   → For backtesting, use SIMULATION_MODE=true")
        except Exception as e:
            print(f"⚠️  Could not validate trading date: {e}")

    if not simulation_mode and use_alpaca:
        # 안전 확인
        confirm = os.getenv("CONFIRM_REAL_TRADING", "false").lower()
        if confirm != "true":
            print("\n⚠️  REAL TRADING MODE REQUIRES CONFIRMATION")
            print("   Set CONFIRM_REAL_TRADING=true to proceed with real trades")
            print("   Falling back to simulation mode for safety")
            simulation_mode = True

    executor = TradeExecutor(
        simulation_mode=simulation_mode,
        use_alpaca=use_alpaca
    )
    executor.execute_decision(decision_file, trading_data_file)

    print("\n✅ Trade execution completed!")


if __name__ == "__main__":
    main()
