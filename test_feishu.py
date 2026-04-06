import asyncio
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from src.utils.webhook_notifier import WebhookNotifier

async def test():
    print("🧪 正在发送飞书测试消息...")
    notifier = WebhookNotifier()
    await notifier.notify(
        event_type="system", 
        data={"msg": "🚀 [进策智算] 飞书通知测试成功！\n\n机器人已进入“顶级靠谱版”实时监控模式。\n监控标的: BTC, ETH, SOL, PEPE\n扫描频率: 10分钟/次\n大盘审计: 已开启"}, 
        stock_code="SYSTEM"
    )
    print("✅ 测试消息已发出，请检查飞书。")

if __name__ == "__main__":
    asyncio.run(test())
