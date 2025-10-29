"""
Alpaca Markets API 통합 모듈 (alpaca-py 사용)
Paper Trading 및 Live Trading 지원
"""

import os
import time
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest


class AlpacaTrader:
    """Alpaca Markets API를 사용한 거래 실행 클래스 (alpaca-py)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper: bool = True
    ):
        """
        Alpaca API 클라이언트 초기화

        Args:
            api_key: Alpaca API Key
            api_secret: Alpaca API Secret
            paper: True=Paper Trading, False=Live Trading
        """
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET")
        self.paper = paper

        if not self.api_key or not self.api_secret:
            raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET are required")

        try:
            # Trading Client 초기화
            self.trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.api_secret,
                paper=paper
            )

            # Data Client 초기화 (실시간 시세 조회용)
            self.data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.api_secret
            )

            # 연결 테스트
            account = self.trading_client.get_account()
            print(f"✅ Alpaca API connected ({'Paper' if paper else 'Live'} Trading)")
            print(f"   Account: {account.account_number}")
            print(f"   Buying Power: ${float(account.buying_power):,.2f}")

        except Exception as e:
            raise ConnectionError(f"Failed to connect to Alpaca API: {e}")

    def get_account_info(self) -> Dict:
        """계좌 정보 조회"""
        try:
            account = self.trading_client.get_account()
            return {
                "account_number": account.account_number,
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "equity": float(account.equity),
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
                "account_blocked": account.account_blocked
            }
        except Exception as e:
            print(f"⚠️ Error getting account info: {e}")
            return {}

    def get_positions(self) -> Dict[str, float]:
        """현재 보유 포지션 조회"""
        try:
            positions = self.trading_client.get_all_positions()
            result = {}

            for position in positions:
                symbol = position.symbol
                qty = float(position.qty)
                result[symbol] = qty

            # 현금 추가
            account = self.trading_client.get_account()
            result['CASH'] = float(account.cash)

            return result

        except Exception as e:
            print(f"⚠️ Error getting positions: {e}")
            return {'CASH': 0.0}

    def get_current_price(self, symbol: str) -> Optional[float]:
        """현재 주가 조회 (최신 호가)"""
        try:
            request_params = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = self.data_client.get_stock_latest_quote(request_params)

            if symbol in quotes:
                quote = quotes[symbol]
                # Ask price 사용 (매수 시 지불할 가격)
                return float(quote.ask_price) if quote.ask_price > 0 else float(quote.bid_price)

            return None

        except Exception as e:
            print(f"⚠️ Error getting price for {symbol}: {e}")
            return None

    def is_market_open(self) -> bool:
        """시장 개장 여부 확인"""
        try:
            clock = self.trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            print(f"⚠️ Error checking market status: {e}")
            return False

    def place_market_order(
        self,
        symbol: str,
        qty: int,
        side: OrderSide,
        time_in_force: TimeInForce = TimeInForce.DAY
    ) -> Optional[Dict]:
        """
        시장가 주문 실행

        Args:
            symbol: 종목 심볼
            qty: 수량
            side: OrderSide.BUY or OrderSide.SELL
            time_in_force: TimeInForce.DAY, GTC, IOC, FOK

        Returns:
            주문 정보 또는 None
        """
        try:
            # 시장가 주문 요청 생성
            market_order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=time_in_force
            )

            # 주문 제출
            order = self.trading_client.submit_order(market_order_data)

            return {
                'id': order.id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'submitted_at': str(order.submitted_at)
            }

        except Exception as e:
            print(f"⚠️ Order failed for {symbol}: {e}")
            return None

    def wait_for_order_fill(self, order_id: str, timeout: int = 60) -> Optional[Dict]:
        """주문 체결 대기"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                order = self.trading_client.get_order_by_id(order_id)

                # Status를 문자열로 변환해서 비교
                status_str = str(order.status.value) if hasattr(order.status, 'value') else str(order.status)

                if status_str.upper() == 'FILLED':
                    return {
                        'id': order.id,
                        'symbol': order.symbol,
                        'qty': float(order.filled_qty),
                        'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else 0.0,
                        'status': status_str
                    }
                elif status_str.upper() in ['CANCELED', 'EXPIRED', 'REJECTED']:
                    print(f"⚠️ Order {order_id} status: {status_str}")
                    return None

                time.sleep(1)  # 1초 대기

            except Exception as e:
                print(f"⚠️ Error checking order status: {e}")
                time.sleep(1)
                continue  # 에러 발생해도 계속 시도

        print(f"⚠️ Order {order_id} timeout after {timeout}s")
        return None

    def execute_buy(self, symbol: str, qty: int) -> Tuple[bool, Optional[float], str]:
        """
        매수 실행

        Returns:
            (성공여부, 체결가, 메시지)
        """
        if qty <= 0:
            return False, None, "Invalid quantity"

        print(f"  🔵 Placing BUY order: {qty} shares of {symbol}")

        # 주문 실행
        order = self.place_market_order(symbol, qty, OrderSide.BUY)

        if not order:
            return False, None, "Order placement failed"

        print(f"     Order ID: {order['id']}, Status: {order['status']}")

        # 체결 대기
        filled_order = self.wait_for_order_fill(order['id'])

        if filled_order:
            price = filled_order['filled_avg_price']
            print(f"     ✅ Filled at ${price:.2f}")
            return True, price, f"Bought {qty} shares at ${price:.2f}"
        else:
            return False, None, "Order not filled"

    def execute_sell(self, symbol: str, qty: int) -> Tuple[bool, Optional[float], str]:
        """
        매도 실행

        Returns:
            (성공여부, 체결가, 메시지)
        """
        if qty <= 0:
            return False, None, "Invalid quantity"

        print(f"  🔴 Placing SELL order: {qty} shares of {symbol}")

        # 주문 실행
        order = self.place_market_order(symbol, qty, OrderSide.SELL)

        if not order:
            return False, None, "Order placement failed"

        print(f"     Order ID: {order['id']}, Status: {order['status']}")

        # 체결 대기
        filled_order = self.wait_for_order_fill(order['id'])

        if filled_order:
            price = filled_order['filled_avg_price']
            print(f"     ✅ Filled at ${price:.2f}")
            return True, price, f"Sold {qty} shares at ${price:.2f}"
        else:
            return False, None, "Order not filled"

    def cancel_all_orders(self) -> bool:
        """모든 미체결 주문 취소"""
        try:
            self.trading_client.cancel_orders()
            print("✅ All pending orders canceled")
            return True
        except Exception as e:
            print(f"⚠️ Error canceling orders: {e}")
            return False

    def close_all_positions(self) -> bool:
        """모든 포지션 청산 (긴급 상황용)"""
        try:
            self.trading_client.close_all_positions(cancel_orders=True)
            print("⚠️ All positions closed")
            return True
        except Exception as e:
            print(f"⚠️ Error closing positions: {e}")
            return False

    def get_portfolio_summary(self) -> Dict:
        """포트폴리오 요약 정보"""
        account_info = self.get_account_info()
        positions = self.get_positions()

        holdings = []
        for symbol, qty in positions.items():
            if symbol != 'CASH' and qty > 0:
                price = self.get_current_price(symbol)
                if price:
                    holdings.append({
                        'symbol': symbol,
                        'qty': qty,
                        'price': price,
                        'value': qty * price
                    })

        return {
            'account': account_info,
            'positions': positions,
            'holdings': holdings,
            'total_value': account_info.get('portfolio_value', 0)
        }
