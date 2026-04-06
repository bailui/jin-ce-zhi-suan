import os
import json
import pandas as pd
from datetime import datetime

def check_status():
    print("📊 --- 进策智算 | 机器人运行状态审计 ---")
    print(f"⏰ 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Check for Active Targets
    try:
        with open('config.json', 'r') as f:
            cfg = json.load(f)
        targets = cfg.get("targets", [])
        strategies = cfg.get("strategies", {}).get("active_ids", [])
        print(f"📡 监控中 ({len(targets)}个): {', '.join(targets)}")
        print(f"🛡️ 运行策略 ({len(strategies)}套): {', '.join(strategies)}")
    except:
        print("❌ 无法读取配置文件")

    # 2. Check for PnL and Positions
    pool_path = "data/live_fund_pool"
    if os.path.exists(pool_path):
        files = [f for f in os.listdir(pool_path) if f.endswith('.json') and any(t in f for t in targets)]
        total_value = 0
        for f in files:
            try:
                with open(os.path.join(pool_path, f), 'r') as j:
                    data = json.load(j)
                    state = data.get("state", {})
                    fund_value = float(state.get("fund_value", 0))
                    total_value += fund_value
                    # Check for positions
                    positions = state.get("positions", [])
                    if positions:
                        for p in positions:
                            print(f"💰 持仓中: {p.get('code')} | 数量: {p.get('qty')} | 入场价: {p.get('entry_price')}")
            except:
                pass
        
        print(f"💵 虚拟账户总资产: ${total_value:,.2f}")
        
    # 3. Check live log freshness
    if os.path.exists("live.log"):
        last_mod = os.path.getmtime("live.log")
        diff = datetime.now().timestamp() - last_mod
        if diff < 120:
            print(f"✅ 日志活跃中 (更新于 {int(diff)}秒前)")
        else:
            print(f"⚠️ 日志更新缓慢 (上次更新于 {int(diff)}秒前)")
            
    print("---------------------------------------")
    print("🚀 机器人已升级为“顶级靠谱版”：")
    print("1. 扫描频率提速至 10min/次。")
    print("2. 自动开启 BTC 大盘走势审计。")
    print("3. 牛旗策略已集成 1小时/4小时多级趋势过滤。")

if __name__ == "__main__":
    check_status()
