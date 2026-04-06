import os
import json
import pandas as pd
from datetime import datetime, timedelta
from src.utils.webhook_notifier import WebhookNotifier

class PerformanceAuditor:
    """
    Performance Auditor: Analyzes past trades and proposes "Evolutionary" improvements.
    """
    def __init__(self, pool_dir="data/live_fund_pool"):
        self.pool_dir = pool_dir
        self.notifier = WebhookNotifier()
        
    def audit_last_24h(self):
        """
        Analyzes trades from the last 24h and generates an audit report.
        """
        print("🕵️ Running 24h Performance Audit...")
        trades = []
        if not os.path.exists(self.pool_dir):
            return "No fund pool directory found."
            
        for f in os.listdir(self.pool_dir):
            if f.endswith('.json'):
                try:
                    with open(os.path.join(self.pool_dir, f), 'r') as j:
                        data = json.load(j)
                        # Extract trade details from state or transactions_all
                        state = data.get("state", {})
                        details = state.get("trade_details", [])
                        trades.extend(details)
                except Exception as e:
                    print(f"Error reading {f}: {e}")
                    
        if not trades:
            return "No trades found in the last 24h to analyze."
            
        # Filter trades from last 24h
        now = datetime.now()
        recent_trades = [t for t in trades if datetime.fromisoformat(t.get('time', now.isoformat())) > (now - timedelta(days=1))]
        
        if not recent_trades:
            return "No recent trades found (last 24h)."
            
        # Basic Metrics
        wins = [t for t in recent_trades if float(t.get('pnl', 0)) > 0]
        losses = [t for t in recent_trades if float(t.get('pnl', 0)) <= 0]
        win_rate = len(wins) / len(recent_trades) if recent_trades else 0
        
        report = {
            "total_trades": len(recent_trades),
            "win_rate": round(win_rate * 100, 2),
            "total_pnl": sum([float(t.get('pnl', 0)) for t in recent_trades]),
            "max_loss": min([float(t.get('pnl', 0)) for t in recent_trades]) if losses else 0,
            "best_trade": max([float(t.get('pnl', 0)) for t in recent_trades]) if wins else 0
        }
        
        # Evolutionary Logic: Analyze stop-losses
        evolution_proposals = []
        if win_rate < 0.6: # If win rate is below 60%, suggest something
            evolution_proposals.append("📈 Win rate is below 60%. Consider tightening ATR stops or adding Volume confirmation.")
        
        if losses:
            avg_loss = sum([float(t.get('pnl', 0)) for t in losses]) / len(losses)
            if abs(avg_loss) > 0.05: # Average loss > 5%
                evolution_proposals.append("🛡️ Average loss is high (>5%). Suggest reducing position size or tightening Hard Stop Loss.")
        
        return report, evolution_proposals

    async def report_evolution(self, report, proposals):
        msg = f"📉 **[进策智算] 机器人自我进化报告**\n"
        msg += f"---------------------------------------\n"
        msg += f"📊 **过去24h战报**:\n"
        msg += f"交易次数: {report['total_trades']}\n"
        msg += f"胜率: {report['win_rate']}%\n"
        msg += f"总盈亏: ${report['total_pnl']:,.2f}\n"
        msg += f"最佳/最差: ${report['best_trade']:,.2f} / ${report['max_loss']:,.2f}\n"
        
        if proposals:
            msg += f"\n🧬 **进化建议 (Evolution Suggestions)**:\n"
            for p in proposals:
                msg += f"- {p}\n"
        else:
            msg += f"\n✅ **当前系统非常稳健，无须立即调优。**"
            
        await self.notifier.notify(
            event_type="daily_summary", 
            data={"msg": msg}, 
            stock_code="SYSTEM"
        )
        return msg

if __name__ == "__main__":
    # Test script
    auditor = PerformanceAuditor()
    res = auditor.audit_last_24h()
    if isinstance(res, tuple):
        report, proposals = res
        print(f"Audit Result: {report}")
        print(f"Proposals: {proposals}")
    else:
        print(res)
