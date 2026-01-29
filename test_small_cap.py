#!/usr/bin/env python3
"""
绩优小市值策略单元测试
"""
import unittest
from datetime import datetime, timedelta

from strategies.small_cap_growth import (
    SmallCapGrowthStrategy,
    SmallCapConfig,
    StockFilter,
    GrowthFilter,
    create_small_cap_strategy
)
from strategies.base import Signal


class TestStockFilter(unittest.TestCase):
    """测试股票池过滤"""
    
    def setUp(self):
        self.strategy = create_small_cap_strategy()
        self.today = datetime.now()
    
    def test_filter_st_stocks(self):
        """测试过滤ST股票"""
        stocks = [
            {"symbol": "000001", "name": "正常股票", "list_date": "20200101"},
            {"symbol": "000002", "name": "ST测试", "list_date": "20200101"},
            {"symbol": "000003", "name": "*ST退市", "list_date": "20200101"},
            {"symbol": "000004", "name": "退市整理", "list_date": "20200101"},
        ]
        
        filtered = self.strategy.filter_stock_pool(stocks, self.today)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["symbol"], "000001")
        print("✅ ST股票过滤正常")
    
    def test_filter_new_stocks(self):
        """测试过滤次新股"""
        old_date = (self.today - timedelta(days=300)).strftime("%Y%m%d")
        new_date = (self.today - timedelta(days=100)).strftime("%Y%m%d")
        
        stocks = [
            {"symbol": "000001", "name": "老股票", "list_date": old_date},
            {"symbol": "000002", "name": "次新股", "list_date": new_date},
        ]
        
        filtered = self.strategy.filter_stock_pool(stocks, self.today)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["symbol"], "000001")
        print("✅ 次新股过滤正常")
    
    def test_filter_kcb(self):
        """测试过滤科创板"""
        stocks = [
            {"symbol": "000001", "name": "主板", "list_date": "20200101"},
            {"symbol": "688001", "name": "科创板", "list_date": "20200101"},
        ]
        
        filtered = self.strategy.filter_stock_pool(stocks, self.today)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["symbol"], "000001")
        print("✅ 科创板过滤正常")
    
    def test_filter_cyb(self):
        """测试过滤创业板"""
        stocks = [
            {"symbol": "000001", "name": "主板", "list_date": "20200101"},
            {"symbol": "300001", "name": "创业板", "list_date": "20200101"},
        ]
        
        filtered = self.strategy.filter_stock_pool(stocks, self.today)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["symbol"], "000001")
        print("✅ 创业板过滤正常")
    
    def test_filter_bj(self):
        """测试过滤北交所"""
        stocks = [
            {"symbol": "000001", "name": "主板", "list_date": "20200101"},
            {"symbol": "430001.BJ", "name": "北交所", "list_date": "20200101"},
        ]
        
        filtered = self.strategy.filter_stock_pool(stocks, self.today)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["symbol"], "000001")
        print("✅ 北交所过滤正常")


class TestGrowthFilter(unittest.TestCase):
    """测试成长因子筛选"""
    
    def setUp(self):
        self.strategy = create_small_cap_strategy()
    
    def test_filter_by_median(self):
        """测试中位数筛选"""
        stocks = [
            {"symbol": "A"},
            {"symbol": "B"},
            {"symbol": "C"},
            {"symbol": "D"},
        ]
        
        # A, B 高于中位数；C, D 低于中位数
        financial = {
            "A": {"rev_yoy": 30, "profit_yoy": 25},
            "B": {"rev_yoy": 25, "profit_yoy": 20},
            "C": {"rev_yoy": 10, "profit_yoy": 8},
            "D": {"rev_yoy": 5, "profit_yoy": 3},
        }
        
        filtered = self.strategy.filter_by_growth(stocks, financial)
        
        # 中位数约为 rev=17.5, profit=14
        # A, B 应该被选中
        symbols = [s["symbol"] for s in filtered]
        self.assertIn("A", symbols)
        self.assertIn("B", symbols)
        self.assertNotIn("D", symbols)
        print(f"✅ 中位数筛选正常，选中: {symbols}")
    
    def test_missing_financial_data(self):
        """测试缺失财务数据的处理"""
        stocks = [
            {"symbol": "A"},
            {"symbol": "B"},
        ]
        
        financial = {
            "A": {"rev_yoy": 30, "profit_yoy": 25},
            # B 没有财务数据
        }
        
        filtered = self.strategy.filter_by_growth(stocks, financial)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["symbol"], "A")
        print("✅ 缺失财务数据处理正常")


class TestMarketCapRanking(unittest.TestCase):
    """测试市值排序"""
    
    def setUp(self):
        self.strategy = create_small_cap_strategy(
            top_n=3,
            max_market_cap=100,
            min_market_cap=10
        )
    
    def test_sort_by_float_value(self):
        """测试按流通市值排序"""
        stocks = [
            {"symbol": "A"},
            {"symbol": "B"},
            {"symbol": "C"},
        ]
        
        market = {
            "A": {"float_value": 5000000000},   # 50亿
            "B": {"float_value": 2000000000},   # 20亿
            "C": {"float_value": 8000000000},   # 80亿
        }
        
        ranked = self.strategy.rank_by_market_cap(stocks, market)
        
        # 应该按市值从小到大: B, A, C
        self.assertEqual(ranked[0]["symbol"], "B")
        self.assertEqual(ranked[1]["symbol"], "A")
        self.assertEqual(ranked[2]["symbol"], "C")
        print("✅ 市值排序正常")
    
    def test_market_cap_limits(self):
        """测试市值范围限制"""
        stocks = [
            {"symbol": "A"},
            {"symbol": "B"},
            {"symbol": "C"},
            {"symbol": "D"},
        ]
        
        market = {
            "A": {"float_value": 500000000},     # 5亿 - 太小
            "B": {"float_value": 2000000000},    # 20亿 ✓
            "C": {"float_value": 5000000000},    # 50亿 ✓
            "D": {"float_value": 15000000000},   # 150亿 - 太大
        }
        
        ranked = self.strategy.rank_by_market_cap(stocks, market)
        
        symbols = [s["symbol"] for s in ranked]
        self.assertNotIn("A", symbols)  # 太小
        self.assertNotIn("D", symbols)  # 太大
        self.assertIn("B", symbols)
        self.assertIn("C", symbols)
        print(f"✅ 市值范围限制正常，选中: {symbols}")
    
    def test_top_n_limit(self):
        """测试选股数量限制"""
        stocks = [{"symbol": f"S{i}"} for i in range(10)]
        
        market = {
            f"S{i}": {"float_value": (i + 2) * 1000000000}  # 20-110亿
            for i in range(10)
        }
        
        ranked = self.strategy.rank_by_market_cap(stocks, market)
        
        self.assertEqual(len(ranked), 3)  # top_n=3
        print(f"✅ 选股数量限制正常，选中 {len(ranked)} 只")


class TestFullPipeline(unittest.TestCase):
    """测试完整选股流程"""
    
    def test_select_stocks(self):
        """测试完整选股"""
        strategy = create_small_cap_strategy(
            top_n=3,
            max_market_cap=100,
            min_market_cap=10
        )
        
        today = datetime.now()
        old_date = (today - timedelta(days=500)).strftime("%Y%m%d")
        
        all_stocks = [
            {"symbol": "000001", "name": "优质小盘A", "list_date": old_date},
            {"symbol": "000002", "name": "优质小盘B", "list_date": old_date},
            {"symbol": "000003", "name": "低增长C", "list_date": old_date},
            {"symbol": "000004", "name": "ST问题股", "list_date": old_date},
            {"symbol": "000005", "name": "大盘股D", "list_date": old_date},
            {"symbol": "688001", "name": "科创板E", "list_date": old_date},
        ]
        
        # 需要更多股票来让中位数筛选生效
        financial = {
            "000001": {"rev_yoy": 30, "profit_yoy": 25},   # 高增长
            "000002": {"rev_yoy": 25, "profit_yoy": 20},   # 高增长
            "000003": {"rev_yoy": 5, "profit_yoy": 3},     # 低增长
            "000005": {"rev_yoy": 8, "profit_yoy": 6},     # 低增长（中位数约15）
        }
        
        market = {
            "000001": {"float_value": 3000000000},   # 30亿
            "000002": {"float_value": 5000000000},   # 50亿
            "000003": {"float_value": 2000000000},   # 20亿
            "000005": {"float_value": 50000000000},  # 500亿 - 超限
        }
        
        selected = strategy.select_stocks(
            all_stocks, financial, market, today
        )
        
        print("\n📊 完整选股测试结果:")
        for s in selected:
            print(f"   {s['symbol']} {s['name']} - {s['market_cap_yi']:.0f}亿")
        
        # 验证：由于中位数计算，只有 000001, 000002 增长高于中位数
        # 且 000001 市值更小，应该排在前面
        symbols = [s["symbol"] for s in selected]
        self.assertIn("000001", symbols)  # 高增长小市值
        self.assertNotIn("000003", symbols)  # 低增长
        self.assertNotIn("000004", symbols)  # ST股票
        self.assertNotIn("000005", symbols)  # 市值超限
        self.assertNotIn("688001", symbols)  # 科创板
        
        print("✅ 完整选股流程正常")


class TestAnalyze(unittest.TestCase):
    """测试单股分析接口"""
    
    def test_analyze_with_kline(self):
        """测试 K 线分析"""
        strategy = create_small_cap_strategy()
        
        # 模拟上涨趋势的 K 线
        data = []
        base_price = 10.0
        for i in range(30):
            price = base_price + i * 0.1
            data.append({
                "close": price,
                "open": price - 0.05,
                "high": price + 0.1,
                "low": price - 0.1,
            })
        
        signal = strategy.analyze("TEST", data)
        
        print(f"\n📈 K线分析结果:")
        print(f"   信号: {signal.signal.value}")
        print(f"   原因: {signal.reason}")
        print(f"   置信度: {signal.confidence:.1%}")
        
        self.assertEqual(signal.signal, Signal.BUY)
        print("✅ K线分析正常")


class TestCustomConfig(unittest.TestCase):
    """测试自定义配置"""
    
    def test_allow_cyb(self):
        """测试允许创业板"""
        config = SmallCapConfig(
            stock_filter=StockFilter(exclude_cyb=False)
        )
        strategy = SmallCapGrowthStrategy(config)
        
        today = datetime.now()
        stocks = [
            {"symbol": "300001", "name": "创业板股", "list_date": "20200101"},
        ]
        
        filtered = strategy.filter_stock_pool(stocks, today)
        
        self.assertEqual(len(filtered), 1)
        print("✅ 允许创业板配置正常")
    
    def test_stricter_percentile(self):
        """测试更严格的百分位筛选"""
        config = SmallCapConfig(
            growth_filter=GrowthFilter(
                revenue_percentile=0.7,  # 前30%
                profit_percentile=0.7
            )
        )
        strategy = SmallCapGrowthStrategy(config)
        
        stocks = [{"symbol": f"S{i}"} for i in range(10)]
        
        # 递增的增长率
        financial = {
            f"S{i}": {"rev_yoy": i * 5, "profit_yoy": i * 4}
            for i in range(10)
        }
        
        filtered = strategy.filter_by_growth(stocks, financial)
        
        # 前30%约等于 3-4 只（取决于中位数计算方式）
        # 主要验证严格筛选减少了选股数量
        self.assertLess(len(filtered), 10)
        print(f"✅ 严格百分位配置正常，筛选出 {len(filtered)} 只")


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 绩优小市值策略单元测试")
    print("=" * 60)
    
    # 运行测试
    unittest.main(verbosity=2)
