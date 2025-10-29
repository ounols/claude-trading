"""
Step 3: 거래 실행
Claude Code Action의 결정을 받아서 실제 거래를 실행
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class TradeExecutor:
    """거래 실행 클래스"""

    def __init__(self, data_path: str = "./data", signature: str = "claude-trader"):
        self.data_path = Path(data_path)
        self.signature = signature
        self.position_dir = self.data_path / "agent_data" / signature / "position"
        self.position_file = self.position_dir / "position.jsonl"
        self.log_dir = self.data_path / "agent_data" / signature / "log"

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
    ) -> tuple[bool, Dict[str, float], str]:
        """단일 거래 실행"""
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

        # datetime에서 date 추출
        date = trading_datetime.split('T')[0] if 'T' in trading_datetime else trading_datetime.split()[0]

        # 포지션 저장
        with open(self.position_file, "a") as f:
            f.write(json.dumps({
                "datetime": trading_datetime,
                "date": date,
                "id": current_id + 1,
                "this_action": {
                    "action": action,
                    "symbol": symbol,
                    "amount": amount,
                    "price": price
                },
                "positions": new_position
            }) + "\n")

        return True, new_position, f"Success: {action} {amount} shares of {symbol} at ${price:.2f}"

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
                success, new_position, message = self.execute_trade(
                    action, symbol, amount, price, current_position, current_id + i - 1, trading_datetime
                )

                if success:
                    print(f"  {i}. ✅ {action.upper()} {amount} {symbol} @ ${price:.2f}")
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

    print("🚀 Trade Executor Starting...")

    executor = TradeExecutor()
    executor.execute_decision(decision_file, trading_data_file)

    print("\n✅ Trade execution completed!")


if __name__ == "__main__":
    main()
