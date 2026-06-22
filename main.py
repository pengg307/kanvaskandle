#!/usr/bin/env python3
"""
Backtest main program v1.0
- Parses symbol from CSV filename
- Compares with fusion report contract_info for vertical verification
- Logs to file with symbol and timestamp
- Saves reports with symbol and timestamp
"""

import pandas as pd
import json
import sys
import logging
from datetime import datetime
from pathlib import Path
from backtest_engine import BacktestEngine
from signal_extractor import SignalExtractor
from risk_filter import RiskFilter
from position_sizer import PositionSizer

# ----- Logging setup -----
data_file_arg = sys.argv[1] if len(sys.argv) > 1 else "data/AG20606_15min.csv"
file_name_only = Path(data_file_arg).name
base_name = file_name_only.replace(".csv", "")
if "_" in base_name:
    backtest_symbol = base_name.split("_")[0]
else:
    backtest_symbol = base_name

log_file = f"output/backtest_{base_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
Path("output").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Command: python main.py {' '.join(sys.argv[1:])}")
logger.info(f"Backtest symbol from filename: {backtest_symbol}")

# ----- Utility functions -----
def load_csv(filepath):
    df = pd.read_csv(filepath)
    col_map = {"日期":"datetime","时间":"datetime","开盘":"open","最高":"high","最低":"low","收盘":"close","成交量":"volume"}
    df = df.rename(columns=col_map)
    keep = ["datetime","open","high","low","close","volume"]
    df = df[[c for c in keep if c in df.columns]]
    df["datetime"] = df["datetime"].astype(str)
    return df

def load_fusion(path="output/fusion_result.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def infinite_gen(fusion):
    while True:
        yield fusion

# ----- Main -----
if __name__ == "__main__":
    logger.info(f"Loading data: {data_file_arg}")
    df = load_csv(data_file_arg)
    logger.info(f"Rows: {len(df)}, Range: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")

    fusion_file = "output/fusion_result.json"
    if not Path(fusion_file).exists():
        logger.error(f"Fusion report {fusion_file} missing, run fusion.py first")
        sys.exit(1)
    fusion = load_fusion(fusion_file)
    logger.info(f"Fusion confidence: {fusion.get('confidence_score')}")

    contract = fusion.get("contract_info", {})
    analysis_symbol = contract.get("symbol", "")
    logger.info(f"Analysis symbol: {analysis_symbol}")

    # Vertical backtest check
    is_vertical = False
    if analysis_symbol and backtest_symbol:
        if analysis_symbol[:2].upper() == backtest_symbol[:2].upper():
            is_vertical = True
            backtest_type = "Vertical (Same Symbol)"
        else:
            backtest_type = "Cross-Symbol"
            logger.warning(f"Analysis symbol {analysis_symbol} mismatches backtest symbol {backtest_symbol}, results for reference only")
    else:
        backtest_type = "Unknown (Symbol Missing)"
    logger.info(f"Backtest Type: {backtest_type}")

    # Init modules
    signal_ext = SignalExtractor()
    risk_filt = RiskFilter("config.yaml")
    pos_sizer = PositionSizer("config.yaml")
    engine = BacktestEngine({"15min": df}, signal_ext, risk_filt, pos_sizer, "config.yaml")
    gen = infinite_gen(fusion)
    report = engine.run(fusion_json_generator=gen)

    report["backtest_meta"] = {
        "analysis_symbol": analysis_symbol,
        "backtest_symbol": backtest_symbol,
        "backtest_type": backtest_type,
        "is_vertical": is_vertical,
        "data_file": data_file_arg,
        "fusion_file": fusion_file
    }

    # Print report
    logger.info("===== Backtest Report =====")
    logger.info(f"Initial Equity: {report['initial_equity']:,.2f}")
    logger.info(f"Final Equity: {report['final_equity']:,.2f}")
    logger.info(f"Total Return: {report['total_return']:.2%}")
    logger.info(f"Max Drawdown: {report['max_drawdown']:.2%}")
    logger.info(f"Total Trades: {report['total_trades']}")
    logger.info(f"Win Rate: {report['win_rate']:.2%}")
    if report['profit_factor'] != float('inf'):
        logger.info(f"Profit Factor: {report['profit_factor']:.2f}")
    logger.info(f"Avg Win: {report['avg_win']:,.2f}")
    logger.info(f"Avg Loss: {report['avg_loss']:,.2f}")

    logger.info("===== Trade Details =====")
    for i, t in enumerate(report.get("trades", []), 1):
        logger.info(f"#{i} {t['direction']} | Entry:{t['entry_time']} @ {t['entry_price']:.2f} | Exit:{t['exit_time']} @ {t['exit_price']:.2f} | PnL:{t['pnl']:,.2f} | Reason:{t['exit_reason']}")

    # Save reports
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    summary_file = f"output/report_{backtest_symbol}_{ts}_summary.json"
    trades_file = f"output/report_{backtest_symbol}_{ts}_trades.json"
    summary = {k:v for k,v in report.items() if k not in ["trades","equity_curve"]}
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(trades_file, "w", encoding="utf-8") as f:
        json.dump(report.get("trades",[]), f, ensure_ascii=False, indent=2)
    logger.info(f"Reports saved: {summary_file}, {trades_file}")