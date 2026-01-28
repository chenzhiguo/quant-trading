# 长桥量化交易系统

基于 [长桥 OpenAPI](https://open.longportapp.com/docs) 的量化交易框架，支持策略扫描、信号推送和模拟交易。

> ⚠️ **重要提示**: 当前连接的是**模拟盘**，所有交易操作均为模拟，不涉及真实资金。

## 📋 目录

- [项目结构](#项目结构)
- [账户信息](#账户信息)
- [快速开始](#快速开始)
- [核心模块](#核心模块)
- [交易策略](#交易策略)
- [自选股配置](#自选股配置)
- [定时任务](#定时任务)
- [风控规则](#风控规则)
- [开发指南](#开发指南)

---

## 项目结构

```
quant-trading/
├── .env                   # API 凭证（包含长桥 API Key，勿提交）
├── .gitignore
├── README.md              # 本文档
│
├── config/                # 配置模块
│   ├── __init__.py
│   ├── watchlist.py       # 自选股列表（美股、港股、AI概念等）
│   └── risk_config.json   # 风控配置
│
├── core/                  # 核心模块
│   ├── __init__.py
│   ├── data.py            # 数据获取（行情、K线）
│   ├── trader.py          # 交易执行（集成风控）
│   └── risk.py            # 风险管理模块
│
├── strategies/            # 交易策略
│   ├── __init__.py
│   ├── base.py            # 策略基类 + 技术指标计算
│   ├── ma_cross.py        # 均线交叉策略（金叉/死叉）
│   └── momentum.py        # 动量策略（趋势追踪 + RSI）
│
├── data/                  # 数据目录（自动生成）
│   ├── trades.jsonl       # 交易记录
│   ├── risk_events.jsonl  # 风控事件日志
│   └── risk_state.json    # 风控状态
│
├── main.py                # 交互式主程序（账户、行情、信号）
├── scan_signals.py        # 信号扫描脚本（供 cron 调用）
├── monitor_stops.py       # 止损止盈监控脚本
└── test_connection.py     # API 连接测试
```

---

## 账户信息

| 项目 | 值 |
|------|-----|
| **账户类型** | 模拟盘 (Paper Trading) |
| **模拟资金** | HKD 800,000 |
| **港股行情** | Level 1 实时 |
| **美股行情** | Nasdaq Basic |
| **A股行情** | Level 1 实时 |

---

## 快速开始

### 1. 环境准备

```bash
# 进入项目目录
cd ~/clawd/quant-trading

# 激活虚拟环境
source .venv/bin/activate
```

### 2. 测试 API 连接

```bash
python test_connection.py
```

成功输出示例：
```
✅ 行情 API 连接成功
✅ 交易 API 连接成功
账户类型: 模拟盘
```

### 3. 运行主程序

```bash
python main.py
```

输出内容：
- 💰 账户资金余额
- 📊 当前持仓
- 📈 实时行情（默认显示 5 只）
- 🔍 信号扫描结果

### 4. 运行信号扫描（推送用）

```bash
# 格式化报告（适合消息推送）
python scan_signals.py

# JSON 格式输出（适合程序解析）
python scan_signals.py --json
```

---

## 核心模块

### 数据获取 (`core/data.py`)

`DataFetcher` 类封装了长桥行情 API：

| 方法 | 功能 | 返回值 |
|------|------|--------|
| `get_realtime_quotes(symbols)` | 获取实时行情 | 行情列表 |
| `get_candlesticks(symbol, period, count)` | 获取 K 线数据 | K 线列表 |
| `get_quote_with_change(symbols)` | 获取行情+涨跌幅 | 字典列表 |
| `get_kline_df(symbol, days)` | 获取 K 线（字典格式） | `[{date, open, high, low, close, volume}, ...]` |

**使用示例：**

```python
from core.data import get_fetcher

fetcher = get_fetcher()

# 获取 NVDA 最近 50 天日K
data = fetcher.get_kline_df("NVDA.US", days=50)

# 获取实时行情
quotes = fetcher.get_quote_with_change(["AAPL.US", "GOOGL.US"])
```

### 交易执行 (`core/trader.py`)

`Trader` 类封装了长桥交易 API：

| 方法 | 功能 | 说明 |
|------|------|------|
| `get_account_balance()` | 查询账户余额 | 返回各币种余额 |
| `get_positions()` | 查询持仓 | 返回持仓列表 |
| `get_today_orders()` | 查询今日订单 | - |
| `submit_order(...)` | 提交订单 | 支持限价/市价 |
| `cancel_order(order_id)` | 取消订单 | - |

**Dry Run 模式（默认开启）：**

```python
from core.trader import get_trader

# dry_run=True（默认）：只打印，不实际下单
trader = get_trader(dry_run=True)
trader.submit_order("AAPL.US", "buy", 10, price=150.0)
# 输出: 🔔 [DRY RUN] BUY 10 AAPL.US @ 150.0

# dry_run=False：实际下单（模拟盘）
trader = get_trader(dry_run=False)
```

---

## 交易策略

所有策略继承自 `BaseStrategy`，实现 `analyze(symbol, data)` 方法返回 `TradeSignal`。

### 信号类型

```python
class Signal(Enum):
    BUY = "BUY"    # 买入
    SELL = "SELL"  # 卖出
    HOLD = "HOLD"  # 持有/观望
```

### 信号结构

```python
@dataclass
class TradeSignal:
    symbol: str        # 股票代码
    signal: Signal     # 信号类型
    price: float       # 当前价格
    reason: str        # 信号原因
    confidence: float  # 置信度 (0-1)
    timestamp: datetime
```

---

### 策略 1: 均线交叉 (`MACrossStrategy`)

**原理：** 短期均线与长期均线的交叉判断趋势转换。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `short_period` | 5 | 短期均线周期 |
| `long_period` | 20 | 长期均线周期 |

**信号规则：**

| 信号 | 条件 | 置信度计算 |
|------|------|------------|
| 🟢 **买入（金叉）** | MA5 从下方上穿 MA20 | 均线差距越大，置信度越高 |
| 🔴 **卖出（死叉）** | MA5 从上方下穿 MA20 | 均线差距越大，置信度越高 |
| ⚪ **持有** | 无交叉发生 | 0.5 |

**使用示例：**

```python
from strategies.ma_cross import MACrossStrategy

strategy = MACrossStrategy(short_period=5, long_period=20)
signal = strategy.analyze("NVDA.US", kline_data)
print(signal)
# 🟢 BUY NVDA.US @ 188.52 (12%) - MA5上穿MA20 (金叉)
```

---

### 策略 2: 动量策略 (`MomentumStrategy`)

**原理：** 追踪强势股票，结合 RSI 过滤超买超卖。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `lookback` | 20 | 动量计算周期（天） |
| `rsi_period` | 14 | RSI 计算周期 |
| `rsi_oversold` | 30 | RSI 超卖阈值 |
| `rsi_overbought` | 70 | RSI 超买阈值 |

**信号规则：**

| 信号 | 条件 | 说明 |
|------|------|------|
| 🟢 **买入** | 20日涨幅 > 5% 且 RSI < 70 | 强势但未超买 |
| 🔴 **卖出** | RSI > 70（超买） | 技术性回调风险 |
| 🔴 **卖出** | 20日跌幅 < -5% | 趋势走弱 |
| ⚪ **持有** | 其他情况 | - |

**使用示例：**

```python
from strategies.momentum import MomentumStrategy

strategy = MomentumStrategy(lookback=20, rsi_period=14)
signal = strategy.analyze("GOOGL.US", kline_data)
print(signal)
# 🟢 BUY GOOGL.US @ 334.55 (15%) - 20日涨幅 6.7%, RSI 69
```

---

### 技术指标（基类提供）

`BaseStrategy` 提供以下技术指标计算方法：

```python
# 移动平均线
ma = strategy.calculate_ma(data, period=20, key="close")

# RSI（相对强弱指数）
rsi = strategy.calculate_rsi(data, period=14)
```

---

## 自选股配置

编辑 `config/watchlist.py` 管理自选股：

```python
# 美股科技股
US_TECH = [
    "AAPL.US",   # 苹果
    "MSFT.US",   # 微软
    "GOOGL.US",  # 谷歌
    "NVDA.US",   # 英伟达
    # ...
]

# 美股 AI 概念
US_AI = [
    "NVDA.US",   # 英伟达
    "AMD.US",    # AMD
    "PLTR.US",   # Palantir
    # ...
]

# 港股科技
HK_TECH = [
    "0700.HK",   # 腾讯
    "9988.HK",   # 阿里巴巴
    # ...
]
```

**获取自选股：**

```python
from config.watchlist import get_watchlist

# 获取美股科技股
symbols = get_watchlist("us_tech")

# 获取所有自选股
symbols = get_watchlist("all")

# 可用分类: default, us_tech, us_ai, hk_tech, all
```

---

## 定时任务

系统通过 Clawdbot Cron 实现定时信号扫描：

| 任务名 | Cron 表达式 | 时间 (GMT+8) | 说明 |
|--------|-------------|--------------|------|
| `quant-signal-scan` | `30 21 * * 1-5` | 周一至周五 21:30 | 美股开盘前扫描 |
| `quant-signal-mid` | `0 0 * * 2-6` | 周二至周六 00:00 | 盘中扫描 |
| `quant-signal-close` | `30 3 * * 2-6` | 周二至周六 03:30 | 收盘前扫描 |

**美股交易时间（北京时间）：**
- 夏令时: 21:30 - 04:00
- 冬令时: 22:30 - 05:00

**手动触发扫描：**

```bash
cd ~/clawd/quant-trading
source .venv/bin/activate
python scan_signals.py
```

---

## 风控模块

系统内置完整的风控管理模块 (`core/risk.py`)，支持自动化风险控制。

### 风控配置

配置文件：`config/risk_config.json`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_single_position_pct` | 10% | 单笔最大仓位 |
| `max_total_position_pct` | 80% | 总仓位上限 |
| `min_cash_reserve_pct` | 20% | 最低现金保留 |
| `default_stop_loss_pct` | 5% | 默认止损线 |
| `default_take_profit_pct` | 15% | 默认止盈线 |
| `daily_loss_limit_pct` | 3% | 每日最大亏损 |
| `daily_trade_limit` | 20 | 每日最大交易次数 |
| `max_order_value` | 50000 | 单笔最大金额 |
| `order_cooldown_seconds` | 60 | 同一股票下单冷却 |

### 核心功能

**1. 订单验证**

```python
from core.trader import get_trader

trader = get_trader()

# 下单时自动进行风控检查
order = trader.submit_order("AAPL.US", "buy", 10, 150.0)
# 如果违反风控规则，订单会被拒绝并返回原因
```

**2. 止损止盈监控**

```python
# 检查并执行止损止盈
executed = trader.check_and_execute_stops()

# 或使用监控脚本
# python monitor_stops.py
```

**3. 智能仓位计算**

```python
# 自动计算合适的买入数量
order = trader.submit_order_with_size(
    symbol="NVDA.US",
    side="buy",
    price=188.50,
    risk_pct=0.08  # 使用 8% 仓位
)
```

**4. 紧急停止**

```python
# 紧急停止所有交易
trader.emergency_stop("市场异常波动")

# 恢复交易
trader.resume_trading()
```

**5. 风险报告**

```python
report = trader.get_risk_report()
print(report)
```

### 止损止盈监控

使用 `monitor_stops.py` 定期检查持仓并执行止损止盈：

```bash
# 检查并执行止损止盈
python monitor_stops.py

# 仅输出风险报告（不执行交易）
python monitor_stops.py --report-only

# 检查后发送通知
python monitor_stops.py --notify
```

可以配置为定时任务，在交易时段每隔 5-10 分钟执行一次。

### 交易日志

所有交易记录保存在 `data/` 目录：
- `trades.jsonl` - 交易记录
- `risk_events.jsonl` - 风控事件
- `risk_state.json` - 风控状态

---

## 开发指南

### 添加新策略

1. 在 `strategies/` 目录创建新文件，如 `rsi_reversal.py`

2. 继承 `BaseStrategy` 并实现 `analyze` 方法：

```python
from .base import BaseStrategy, TradeSignal, Signal

class RSIReversalStrategy(BaseStrategy):
    name = "RSI Reversal"
    description = "RSI 超卖反转策略"
    
    def __init__(self, rsi_period: int = 14, oversold: int = 30):
        super().__init__()
        self.rsi_period = rsi_period
        self.oversold = oversold
    
    def analyze(self, symbol: str, data: list) -> TradeSignal:
        # 计算 RSI
        rsi_values = self.calculate_rsi(data, self.rsi_period)
        current_rsi = rsi_values[-1] if rsi_values else 50
        current_price = data[-1]["close"]
        
        # 超卖反转买入
        if current_rsi < self.oversold:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.BUY,
                price=current_price,
                reason=f"RSI 超卖反转 ({current_rsi:.0f} < {self.oversold})",
                confidence=min((self.oversold - current_rsi) / 30, 1.0)
            )
        
        return TradeSignal(
            symbol=symbol,
            signal=Signal.HOLD,
            price=current_price,
            reason=f"RSI {current_rsi:.0f}",
            confidence=0.5
        )
```

3. 在 `scan_signals.py` 中添加新策略：

```python
from strategies.rsi_reversal import RSIReversalStrategy

strategies = [
    MACrossStrategy(short_period=5, long_period=20),
    MomentumStrategy(lookback=20, rsi_period=14),
    RSIReversalStrategy(rsi_period=14, oversold=30),  # 新增
]
```

### 环境变量配置

`.env` 文件需包含长桥 API 凭证：

```bash
LONGPORT_APP_KEY=your_app_key
LONGPORT_APP_SECRET=your_app_secret
LONGPORT_ACCESS_TOKEN=your_access_token
```

获取方式：[长桥开发者中心](https://open.longportapp.com/)

---

## 常见问题

### Q: 信号扫描显示的价格是实时的吗？

A: 扫描使用的是最近一个交易日的**收盘价**（日 K 线数据），而非实时盘口价格。美股收盘后扫描的是当天数据，未开盘时扫描的是前一交易日数据。

### Q: 如何切换到实盘？

A: 需要在长桥开通实盘账户，并更新 `.env` 中的 API 凭证。代码层面需将 `Trader` 的 `dry_run` 参数设为 `False`。

### Q: 为什么有些股票显示"无数据"？

A: 可能原因：
1. 股票代码格式错误（需要 `AAPL.US` 格式）
2. 该股票不在订阅行情范围内
3. API 请求频率限制

---

## 许可证

仅供学习研究使用，不构成投资建议。

---

*最后更新: 2026-01-28*
