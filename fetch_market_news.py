"""
Step 1.5: 시장 뉴스 수집
Jina Search & Reader API를 사용하여 시장 및 섹터 뉴스 수집
yfinance를 사용하여 종목별 뉴스 수집
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import re
from dotenv import load_dotenv
import yfinance as yf
import xml.etree.ElementTree as ET

# Windows 환경에서 UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# .env 파일 로드
load_dotenv()


class MarketNewsCollector:
    """Jina AI를 사용한 시장 뉴스 수집 클래스"""

    # RSS Feed URLs
    KAGI_BUSINESS_RSS_URL = "https://news.kagi.com/business.xml"
    CNBC_STOCK_NEWS_RSS_URL = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
    NASDAQ_STOCK_RSS_URL_TEMPLATE = "https://www.nasdaq.com/feed/rssoutbound?symbol={symbol}"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("JINA_API_KEY")
        self.has_jina_api = bool(self.api_key)

        if not self.has_jina_api:
            print("⚠️ JINA_API_KEY not found - will skip market/sector news collection")
            print("   Only stock-specific news (via yfinance) will be collected")

        self.search_url = "https://s.jina.ai/"
        self.reader_url = "https://r.jina.ai/"

    def parse_date_to_standard(self, date_str: str) -> str:
        """다양한 날짜 형식을 표준 형식(YYYY-MM-DD HH:MM:SS)으로 변환"""
        if not date_str or date_str == 'unknown':
            return '1900-01-01 00:00:00'

        try:
            now = datetime.now()

            # 상대 시간 처리: "4 hours ago", "1 day ago"
            if 'ago' in date_str.lower():
                numbers = re.findall(r'\d+', date_str)
                if not numbers:
                    return now.strftime('%Y-%m-%d %H:%M:%S')

                value = int(numbers[0])
                if 'hour' in date_str.lower():
                    target_date = now - timedelta(hours=value)
                elif 'day' in date_str.lower():
                    target_date = now - timedelta(days=value)
                elif 'week' in date_str.lower():
                    target_date = now - timedelta(weeks=value)
                elif 'month' in date_str.lower():
                    target_date = now - timedelta(days=value * 30)
                else:
                    target_date = now
                return target_date.strftime('%Y-%m-%d %H:%M:%S')

            # ISO 8601 형식: "2025-10-01T08:19:28+00:00"
            if 'T' in date_str:
                date_part = date_str.split('+')[0].split('-')[0:3]
                date_part = '-'.join(date_part[:3])
                if len(date_part.split('T')) > 1:
                    parsed_date = datetime.strptime(date_part, '%Y-%m-%dT%H:%M:%S')
                else:
                    parsed_date = datetime.strptime(date_part, '%Y-%m-%d')
                return parsed_date.strftime('%Y-%m-%d %H:%M:%S')

            # 일반 형식: "May 31, 2025" 또는 "2025-05-31"
            if ',' in date_str:
                parsed_date = datetime.strptime(date_str.strip(), '%b %d, %Y')
            elif '-' in date_str and len(date_str) == 10:
                parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                return now.strftime('%Y-%m-%d %H:%M:%S')

            return parsed_date.strftime('%Y-%m-%d %H:%M:%S')

        except Exception as e:
            print(f"⚠️ Date parsing error for '{date_str}': {e}")
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def search(self, query: str, max_results: int = 5, cutoff_date: Optional[str] = None) -> List[str]:
        """Jina Search API로 검색 수행"""
        url = f'{self.search_url}?q={query}&n={max_results}'
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json',
            'X-Respond-With': 'no-content'
        }

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            filtered_urls = []
            for item in data.get('data', []):
                raw_date = item.get('date', 'unknown')
                standardized_date = self.parse_date_to_standard(raw_date)

                # 날짜 필터링 (cutoff_date 이전 정보만)
                if cutoff_date and standardized_date > cutoff_date:
                    continue

                filtered_urls.append({
                    'url': item.get('url'),
                    'title': item.get('title', 'No title'),
                    'description': item.get('description', ''),
                    'date': standardized_date
                })

            print(f"  Found {len(filtered_urls)} results for '{query}'")
            return filtered_urls

        except Exception as e:
            print(f"⚠️ Search error for '{query}': {e}")
            return []

    def read_url(self, url: str) -> Optional[Dict]:
        """Jina Reader API로 URL 컨텐츠 스크래핑"""
        reader_url = f'{self.reader_url}{url}'
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
            'X-Timeout': '10',
            'X-With-Generated-Alt': 'true',
        }

        try:
            response = requests.get(reader_url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            content = data.get('data', {}).get('content', '')
            # 컨텐츠 길이 제한 (첫 2000자)
            if len(content) > 2000:
                content = content[:2000] + '...'

            return {
                'url': url,
                'title': data.get('data', {}).get('title', 'No title'),
                'description': data.get('data', {}).get('description', ''),
                'content': content,
                'publish_time': data.get('data', {}).get('publishedTime', 'unknown')
            }

        except Exception as e:
            print(f"⚠️ Reader error for '{url}': {e}")
            return None

    def fetch_cnbc_stock_news(self, cutoff_date: str, max_news: int = 10) -> List[Dict]:
        """CNBC 주식 뉴스 RSS 피드에서 뉴스 가져오기"""
        try:
            print(f"  Fetching CNBC stock news from RSS...")
            response = requests.get(self.CNBC_STOCK_NEWS_RSS_URL, timeout=15)
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)
            news_items = []

            # RSS 2.0 형식 파싱
            for item in root.findall('.//item')[:max_news]:
                title = item.find('title')
                link = item.find('link')
                description = item.find('description')
                pub_date = item.find('pubDate')

                # 날짜 파싱 (RFC 822 형식)
                publish_time = 'unknown'
                if pub_date is not None and pub_date.text:
                    try:
                        date_str = pub_date.text
                        # +0000 형식의 timezone을 제거하고 파싱
                        if '+0000' in date_str or '-0000' in date_str:
                            date_str = date_str.replace('+0000', '').replace('-0000', '').strip()
                            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
                        elif ' GMT' in date_str or ' UTC' in date_str:
                            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z')
                        else:
                            # 기타 형식은 기존 parse_date_to_standard 사용
                            publish_time = self.parse_date_to_standard(date_str)
                            dt = None

                        if dt:
                            publish_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception as e:
                        print(f"    ⚠️ Date parsing error: {e}")
                        publish_time = self.parse_date_to_standard(pub_date.text)

                # cutoff_date 필터링
                if publish_time != 'unknown' and publish_time > cutoff_date:
                    continue

                news_items.append({
                    'url': link.text if link is not None else '',
                    'title': title.text if title is not None else 'No title',
                    'description': description.text if description is not None else '',
                    'content': description.text if description is not None else '',
                    'publish_time': publish_time,
                    'source': 'CNBC Stock News'
                })

            print(f"    ✓ Found {len(news_items)} CNBC stock news items")
            return news_items

        except Exception as e:
            print(f"⚠️ CNBC RSS fetch error: {e}")
            return []

    def fetch_nasdaq_stock_news(self, symbol: str, cutoff_date: str, max_news: int = 5) -> List[Dict]:
        """NASDAQ RSS 피드에서 종목별 뉴스 가져오기"""
        rss_url = self.NASDAQ_STOCK_RSS_URL_TEMPLATE.format(symbol=symbol)

        try:
            # User-Agent 헤더 추가 (일부 사이트는 봇 차단)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(rss_url, headers=headers, timeout=30)
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)
            news_items = []

            # RSS 2.0 형식 파싱
            for item in root.findall('.//item')[:max_news]:
                title = item.find('title')
                link = item.find('link')
                description = item.find('description')
                pub_date = item.find('pubDate')

                # 날짜 파싱 (RFC 822 형식)
                publish_time = 'unknown'
                if pub_date is not None and pub_date.text:
                    try:
                        date_str = pub_date.text
                        # +0000 형식의 timezone을 제거하고 파싱
                        if '+0000' in date_str or '-0000' in date_str:
                            date_str = date_str.replace('+0000', '').replace('-0000', '').strip()
                            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
                        elif ' GMT' in date_str or ' UTC' in date_str:
                            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z')
                        else:
                            # 기타 형식은 기존 parse_date_to_standard 사용
                            publish_time = self.parse_date_to_standard(date_str)
                            dt = None

                        if dt:
                            publish_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception as e:
                        print(f"    ⚠️ Date parsing error: {e}")
                        publish_time = self.parse_date_to_standard(pub_date.text)

                # cutoff_date 필터링
                if publish_time != 'unknown' and publish_time > cutoff_date:
                    continue

                news_items.append({
                    'url': link.text if link is not None else '',
                    'title': title.text if title is not None else 'No title',
                    'description': description.text if description is not None else '',
                    'content': description.text if description is not None else '',
                    'publish_time': publish_time,
                    'source': f'NASDAQ - {symbol}'
                })

            return news_items

        except Exception as e:
            print(f"    ⚠️ NASDAQ RSS fetch error for {symbol}: {e}")
            return []

    def fetch_kagi_business_news(self, cutoff_date: str, max_news: int = 10) -> List[Dict]:
        """Kagi 비즈니스 뉴스 RSS 피드에서 뉴스 가져오기"""
        try:
            print(f"  Fetching Kagi business news from RSS...")
            response = requests.get(self.KAGI_BUSINESS_RSS_URL, timeout=15)
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)
            news_items = []

            # RSS 2.0 형식 파싱
            for item in root.findall('.//item')[:max_news]:
                title = item.find('title')
                link = item.find('link')
                description = item.find('description')
                pub_date = item.find('pubDate')

                # 날짜 파싱 (RFC 822 형식: "Mon, 28 Oct 2024 12:00:00 +0000")
                publish_time = 'unknown'
                if pub_date is not None and pub_date.text:
                    try:
                        date_str = pub_date.text
                        # +0000 형식의 timezone을 제거하고 파싱
                        if '+0000' in date_str or '-0000' in date_str:
                            date_str = date_str.replace('+0000', '').replace('-0000', '').strip()
                            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
                        elif ' GMT' in date_str or ' UTC' in date_str:
                            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z')
                        else:
                            # 기타 형식은 기존 parse_date_to_standard 사용
                            publish_time = self.parse_date_to_standard(date_str)
                            dt = None

                        if dt:
                            publish_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception as e:
                        print(f"    ⚠️ Date parsing error: {e}")
                        publish_time = self.parse_date_to_standard(pub_date.text)

                # cutoff_date 필터링
                if publish_time != 'unknown' and publish_time > cutoff_date:
                    continue

                news_items.append({
                    'url': link.text if link is not None else '',
                    'title': title.text if title is not None else 'No title',
                    'description': description.text if description is not None else '',
                    'content': description.text if description is not None else '',
                    'publish_time': publish_time,
                    'source': 'Kagi Business News'
                })

            print(f"    ✓ Found {len(news_items)} business news items")
            return news_items

        except Exception as e:
            print(f"⚠️ Kagi RSS fetch error: {e}")
            return []

    def get_stock_news_yfinance(self, symbol: str, max_news: int = 3) -> List[Dict]:
        """yfinance를 사용하여 종목 뉴스 가져오기"""
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news

            if not news:
                return []

            # 최대 개수만큼만 가져오기
            news_items = []
            for item in news[:max_news]:
                # 중첩된 content 구조 처리
                content = item.get('content', {})

                # pubDate를 datetime으로 변환 (ISO 8601 형식)
                pub_date_str = content.get('pubDate', '')
                try:
                    if pub_date_str:
                        # ISO 8601 형식 파싱: "2025-10-28T20:03:53Z"
                        pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                        publish_time = pub_date.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        publish_time = 'unknown'
                except Exception:
                    publish_time = 'unknown'

                # 뉴스 URL
                canonical_url = content.get('canonicalUrl', {})
                url = canonical_url.get('url', '')

                # Provider 정보
                provider = content.get('provider', {})
                publisher = provider.get('displayName', 'Unknown')

                news_items.append({
                    'url': url,
                    'title': content.get('title', 'No title'),
                    'description': content.get('description', ''),
                    'content': content.get('summary', ''),  # summary를 content로 사용
                    'publish_time': publish_time,
                    'publisher': publisher
                })

            return news_items

        except Exception as e:
            print(f"⚠️ yfinance news error for '{symbol}': {e}")
            return []

    def collect_market_news(self, trading_date: str, symbols: List[str]) -> Dict:
        """시장 뉴스 및 주요 종목 뉴스 수집"""
        print(f"\n📰 Collecting market news for {trading_date}...")

        # 거래일 기준으로 cutoff (미래 정보 차단)
        cutoff_datetime = f"{trading_date} 23:59:59"

        news_data = {
            'trading_date': trading_date,
            'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'market_overview': [],
            'sector_news': [],
            'top_stocks_news': {}
        }

        # 1. Kagi 비즈니스 뉴스 수집 (항상 실행)
        print("\n1️⃣ Collecting Kagi business news...")
        kagi_news = self.fetch_kagi_business_news(cutoff_datetime, max_news=5)
        news_data['market_overview'].extend(kagi_news)

        # 1-2. CNBC 주식 뉴스 수집 (항상 실행)
        print("\n1-2️⃣ Collecting CNBC stock news...")
        cnbc_news = self.fetch_cnbc_stock_news(cutoff_datetime, max_news=5)
        news_data['market_overview'].extend(cnbc_news)

        # 2. 전체 시장 뉴스 (JINA API 사용 가능할 때만)
        if self.has_jina_api:
            print("\n2️⃣ Collecting general market news...")
            market_queries = [
                "NASDAQ stock market news today",
                "US stock market outlook",
                "tech stocks market analysis"
            ]

            for query in market_queries:
                results = self.search(query, max_results=2, cutoff_date=cutoff_datetime)
                for result in results[:1]:  # 각 쿼리당 1개씩만
                    article = self.read_url(result['url'])
                    if article:
                        news_data['market_overview'].append(article)

            # 3. 섹터 뉴스
            print("\n3️⃣ Collecting sector news...")
            sector_queries = [
                "technology sector stocks",
                "semiconductor industry news"
            ]

            for query in sector_queries:
                results = self.search(query, max_results=2, cutoff_date=cutoff_datetime)
                for result in results[:1]:
                    article = self.read_url(result['url'])
                    if article:
                        news_data['sector_news'].append(article)
        else:
            print("\n⏭️  Skipping market/sector news (no JINA API key)")

        # 4. 주요 종목 뉴스 (시가총액 상위 20개만) - yfinance + NASDAQ RSS 사용
        print("\n4️⃣ Collecting top stocks news (using yfinance + NASDAQ RSS)...")
        top_symbols = symbols[:20]  # 상위 20개만

        for symbol in top_symbols:
            print(f"  Fetching news for {symbol}...")

            # yfinance 뉴스
            yf_news_items = self.get_stock_news_yfinance(symbol, max_news=2)

            # NASDAQ RSS 뉴스
            nasdaq_news_items = self.fetch_nasdaq_stock_news(symbol, cutoff_datetime, max_news=2)

            # 두 소스 합치기
            all_news_items = yf_news_items + nasdaq_news_items

            if all_news_items:
                # cutoff_date 이전 뉴스만 필터링
                filtered_news = []
                for item in all_news_items:
                    if item['publish_time'] <= cutoff_datetime:
                        filtered_news.append(item)

                if filtered_news:
                    news_data['top_stocks_news'][symbol] = filtered_news
                    print(f"    ✓ Found {len(filtered_news)} news items (yfinance: {len(yf_news_items)}, NASDAQ: {len(nasdaq_news_items)})")
                else:
                    print(f"    ⚠ No news within cutoff date")
            else:
                print(f"    ⚠ No news available")

        # 통계 출력
        print(f"\n✅ News collection complete:")
        print(f"   - Market overview: {len(news_data['market_overview'])} articles")
        print(f"   - Sector news: {len(news_data['sector_news'])} articles")
        print(f"   - Stock news: {len(news_data['top_stocks_news'])} stocks")

        return news_data


def main():
    """메인 실행 함수"""
    # 거래 모드 확인
    use_alpaca = os.getenv("USE_ALPACA", "false").lower() == "true"
    simulation_mode = os.getenv("SIMULATION_MODE", "true").lower() == "true"

    # 거래 날짜
    trading_date = os.getenv("TRADING_DATE")
    if not trading_date:
        trading_datetime = os.getenv("TRADING_DATETIME")
        if trading_datetime:
            trading_date = trading_datetime.split('T')[0] if 'T' in trading_datetime else trading_datetime.split()[0]
        else:
            now = datetime.now()
            if now.weekday() >= 5:  # 주말
                print("⚠️ Weekend - No trading")
                return
            trading_date = now.strftime("%Y-%m-%d")
    else:
        # Alpaca 모드에서 과거 날짜 입력 시 경고 및 무시
        if use_alpaca and not simulation_mode:
            today = datetime.now().strftime("%Y-%m-%d")
            if trading_date != today:
                print(f"\n⚠️  WARNING: Alpaca mode cannot use past dates for news")
                print(f"   Requested date: {trading_date}")
                print(f"   Current date: {today}")
                print(f"   → Ignoring past date and using today's date")
                print(f"   → For backtesting, use SIMULATION_MODE=true\n")
                trading_date = today

    print(f"📅 Trading Date: {trading_date}")

    # NASDAQ 100 심볼 (prepare_trading_data.py와 동일)
    symbols = [
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

    # 뉴스 수집
    collector = MarketNewsCollector()
    news_data = collector.collect_market_news(trading_date, symbols)

    # JSON 파일로 저장
    output_file = Path("market_news.json")
    with open(output_file, "w", encoding='utf-8') as f:
        json.dump(news_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Market news saved to: {output_file}")


if __name__ == "__main__":
    main()
