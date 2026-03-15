# test_data_provider.py
from src.utils.data_provider import DataProvider
from src.utils.tushare_provider import TushareProvider
from src.utils.akshare_provider import AkshareProvider
from src.utils.config_loader import ConfigLoader
from datetime import datetime

def test_fetch():
    print("=== 开始数据源连通性测试 ===")
    
    # 1. Load Config
    config = ConfigLoader()
    source = config.get("data_provider.source", "default")
    print(f"当前配置的数据源: [{source}]")
    
    provider = None
    
    # 2. Initialize Provider based on config
    if source == "tushare":
        token = config.get("data_provider.tushare_token")
        print(f"初始化 TushareProvider (Token: {token[:6]}******)...")
        provider = TushareProvider(token)
    elif source == "akshare":
        print("初始化 AkshareProvider (免费源)...")
        provider = AkshareProvider()
    elif source == "mock":
        from src.utils.data_generator import DataGenerator
        print("初始化 Mock DataGenerator (测试用)...")
        provider = DataGenerator()
    else:
        print("初始化默认 DataProvider (自定义API)...")
        provider = DataProvider()
        
    code = "000001.SZ" # 平安银行
    
    # 3. Test Historical Data (Minute Bar)
    print("\n--- 测试 1: 获取历史分钟数据 ---")
    start = datetime(2023, 6, 1)
    end = datetime(2023, 6, 2) # Get 1 day
    
    print(f"正在请求 {code} 从 {start} 到 {end} 的分钟数据...")
    try:
        # Note: Different providers might have slightly different method signatures or behavior
        # But our cabinets expect `fetch_minute_data(code, start, end)`
        if source == "akshare":
             # Akshare uses simple code usually, let's pass full code, provider handles split
             pass
             
        df = provider.fetch_minute_data(code, start, end)
        
        if not df.empty:
            print(f"✅ 成功! 获取到 {len(df)} 条K线数据")
            print(f"数据范围: {df['dt'].min()} -> {df['dt'].max()}")
            print("前3行数据预览:")
            print(df.head(3))
        else:
            print("❌ 失败: 返回数据为空 (可能原因: Token无效 / 额度耗尽 / 网络超时 / 该时间段无数据)")
            
    except Exception as e:
        print(f"❌ 异常: 请求过程中发生错误 -> {str(e)}")
        
    # 4. Test Real-time Data (Latest Bar)
    print("\n--- 测试 2: 获取最新实时行情 ---")
    try:
        bar = provider.get_latest_bar(code)
        if bar:
            print(f"✅ 成功! 最新行情: {bar}")
        else:
             print("❌ 失败: 未能获取最新行情")
    except Exception as e:
        print(f"❌ 异常: 获取实时行情时出错 -> {str(e)}")

if __name__ == "__main__":
    test_fetch()
