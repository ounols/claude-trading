"""
Claude Code Action Trader 로컬 테스트 스크립트
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


def check_environment():
    """환경 설정 확인"""
    print("🔍 Checking environment...")

    issues = []

    # 데이터 디렉토리 확인
    data_dir = Path("./data")
    if not data_dir.exists():
        print("⚠️ data/ directory not found, will be created")
        data_dir.mkdir(parents=True, exist_ok=True)
    else:
        print("✅ data/ directory exists")

    # merged.jsonl 확인
    merged_file = data_dir / "merged.jsonl"
    if not merged_file.exists():
        issues.append("⚠️ data/merged.jsonl not found. Run fetch_stock_data.py first")
    else:
        size_mb = merged_file.stat().st_size / (1024 * 1024)
        print(f"✅ data/merged.jsonl exists ({size_mb:.2f} MB)")

    # 패키지 확인
    try:
        import yfinance
        print("✅ yfinance package installed")
    except ImportError:
        issues.append("❌ yfinance not installed. Run: pip install yfinance")

    if issues:
        print("\n⚠️ Issues found:")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("\n✅ All checks passed!")
        return True


def test_data_fetch():
    """데이터 수집 테스트"""
    print("\n" + "="*60)
    print("📊 Testing data fetch...")
    print("="*60)

    try:
        import subprocess
        result = subprocess.run(
            ["python", "fetch_stock_data.py"],
            env={**os.environ, "DAYS_BACK": "7"},
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            print("✅ Data fetch successful")
            print(result.stdout[-500:])
        else:
            print("❌ Data fetch failed")
            print(result.stderr[-500:])

    except Exception as e:
        print(f"❌ Error: {e}")


def test_data_preparation():
    """데이터 준비 테스트"""
    print("\n" + "="*60)
    print("📋 Testing data preparation...")
    print("="*60)

    test_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    os.environ["TRADING_DATE"] = test_date

    try:
        import subprocess
        result = subprocess.run(
            ["python", "prepare_trading_data.py"],
            env={**os.environ},
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("✅ Data preparation successful")
            print(result.stdout)

            # 생성된 파일 확인
            if Path("trading_data.json").exists():
                print("\n📄 trading_data.json created:")
                with open("trading_data.json") as f:
                    data = json.load(f)
                    print(f"   - Date: {data.get('date')}")
                    print(f"   - Portfolio value: ${data['portfolio']['total_value']:.2f}")
                    print(f"   - Number of prices: {len(data['market']['prices'])}")

            if Path("trading_prompt.txt").exists():
                print("\n📄 trading_prompt.txt created")
                with open("trading_prompt.txt") as f:
                    lines = f.readlines()
                    print(f"   - Lines: {len(lines)}")

        else:
            print("❌ Data preparation failed")
            print(result.stderr)

    except Exception as e:
        print(f"❌ Error: {e}")


def test_mock_decision():
    """모의 Claude 결정 테스트"""
    print("\n" + "="*60)
    print("🤖 Testing with mock Claude decision...")
    print("="*60)

    # 모의 Claude 결정 생성
    mock_decision = {
        "analysis": "Mock analysis: Market looks stable. Will execute a test buy order.",
        "actions": [
            {"action": "buy", "symbol": "AAPL", "amount": 2}
        ]
    }

    with open("claude_decision.json", "w") as f:
        json.dump(mock_decision, f, indent=2)

    print("✅ Mock decision created:")
    print(f"   - Analysis: {mock_decision['analysis']}")
    print(f"   - Actions: {len(mock_decision['actions'])}")

    # 거래 실행
    try:
        import subprocess
        result = subprocess.run(
            ["python", "execute_trades.py"],
            env={**os.environ},
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("\n✅ Trade execution successful")
            print(result.stdout)
        else:
            print("\n❌ Trade execution failed")
            print(result.stderr)

    except Exception as e:
        print(f"❌ Error: {e}")


def cleanup():
    """임시 파일 정리"""
    print("\n🧹 Cleaning up temporary files...")
    temp_files = ["trading_data.json", "trading_prompt.txt", "claude_decision.json"]

    for f in temp_files:
        if Path(f).exists():
            Path(f).unlink()
            print(f"   - Removed {f}")


def main():
    """메인 테스트 함수"""
    print("🧪 Claude Code Action Trader Test Suite")
    print("="*60)

    # 1. 환경 확인
    if not check_environment():
        print("\n❌ Please fix the issues above and try again")
        print("\n💡 Quick setup:")
        print("  1. Run: pip install -r requirements-claude-action.txt")
        print("  2. Run: python fetch_stock_data.py")
        return

    # 2. 테스트 선택
    print("\nWhat would you like to test?")
    print("  1. Data fetch only")
    print("  2. Data preparation only")
    print("  3. Full workflow (fetch -> prepare -> mock decision -> execute)")
    print("  4. Skip tests (just check environment)")

    choice = input("\nEnter choice (1-4) [default: 3]: ").strip() or "3"

    try:
        if choice == "1":
            test_data_fetch()
        elif choice == "2":
            test_data_preparation()
        elif choice == "3":
            test_data_fetch()
            test_data_preparation()
            test_mock_decision()
        elif choice == "4":
            print("\n✅ Environment check completed")
        else:
            print("Invalid choice")

    finally:
        # 항상 정리
        cleanup()

    print("\n" + "="*60)
    print("🎉 Test suite completed!")
    print("="*60)
    print("\n💡 Next steps:")
    print("  1. Push code to GitHub")
    print("  2. GitHub Actions will use claude-code-action")
    print("  3. No API key needed in secrets!")


if __name__ == "__main__":
    main()
