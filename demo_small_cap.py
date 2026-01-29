#!/usr/bin/env python3
"""
绩优小市值策略 Demo

演示如何使用 SmallCapGrowthStrategy 进行 A 股选股。

策略逻辑：
1. 过滤 ST、次新股、科创板/创业板/北交所
2. 筛选营收同比、净利润同比高于市场中位数的股票
3. 按流通市值从小到大排序，选前 N 只

使用：
    python demo_small_cap.py
"""
import os
import sys
from datetime import datetime
from pprint import pprint

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.small_cap_growth import (
    SmallCapGrowthStrategy,
    SmallCapConfig,
    StockFilter,
    GrowthFilter,
    create_small_cap_strategy
)


def demo_with_mock_data():
    """使用模拟数据演示策略"""
    
    print("=" * 60)
    print("🎯 绩优小市值策略 Demo")
    print("=" * 60)
    
    # 创建策略实例
    strategy = create_small_cap_strategy(
        top_n=5,              # 选前5只
        exclude_cyb=True,     # 排除创业板
        exclude_bj=True,      # 排除北交所
        max_market_cap=100,   # 最大市值100亿
        min_market_cap=10     # 最小市值10亿
    )
    
    print("\n📋 策略配置：")
    pprint(strategy.get_strategy_info())
    
    # 模拟股票数据
    mock_stocks = [
        {"symbol": "000001", "name": "平安银行", "list_date": "19910403"},
        {"symbol": "000002", "name": "万科A", "list_date": "19910129"},
        {"symbol": "000004", "name": "国华网安", "list_date": "19910114"},
        {"symbol": "000005", "name": "ST星源", "list_date": "19901210"},      # ST股票，会被过滤
        {"symbol": "000006", "name": "深振业A", "list_date": "19920427"},
        {"symbol": "000007", "name": "零七股份", "list_date": "19920608"},
        {"symbol": "000008", "name": "神州高铁", "list_date": "19920507"},
        {"symbol": "000009", "name": "中国宝安", "list_date": "19910625"},
        {"symbol": "000010", "name": "美丽生态", "list_date": "19951027"},
        {"symbol": "300001", "name": "特锐德", "list_date": "20091030"},      # 创业板，会被过滤
        {"symbol": "688001", "name": "华兴源创", "list_date": "20190722"},    # 科创板，会被过滤
        {"symbol": "000011", "name": "某新股", "list_date": "20251001"},      # 次新股，会被过滤
    ]
    
    # 模拟财务数据
    mock_financial = {
        "000001": {"rev_yoy": 15.2, "profit_yoy": 12.5},
        "000002": {"rev_yoy": -5.3, "profit_yoy": -10.2},    # 负增长，会被过滤
        "000004": {"rev_yoy": 25.8, "profit_yoy": 30.2},
        "000006": {"rev_yoy": 18.5, "profit_yoy": 22.1},
        "000007": {"rev_yoy": 8.2, "profit_yoy": 5.5},       # 低于中位数
        "000008": {"rev_yoy": 35.6, "profit_yoy": 45.3},
        "000009": {"rev_yoy": 20.1, "profit_yoy": 18.9},
        "000010": {"rev_yoy": 12.3, "profit_yoy": 15.6},
    }
    
    # 模拟市值数据（单位：元）
    mock_market = {
        "000001": {"total_value": 300000000000, "float_value": 250000000000},  # 2500亿，超限
        "000002": {"total_value": 100000000000, "float_value": 80000000000},   # 800亿，超限
        "000004": {"total_value": 5000000000, "float_value": 4500000000},      # 45亿 ✓
        "000006": {"total_value": 8000000000, "float_value": 7000000000},      # 70亿 ✓
        "000007": {"total_value": 3000000000, "float_value": 2500000000},      # 25亿 ✓
        "000008": {"total_value": 6000000000, "float_value": 5500000000},      # 55亿 ✓
        "000009": {"total_value": 15000000000, "float_value": 12000000000},    # 120亿，超限
        "000010": {"total_value": 4000000000, "float_value": 3500000000},      # 35亿 ✓
    }
    
    # 执行选股
    print("\n🔍 开始选股...")
    print("-" * 40)
    
    # Step 1: 过滤股票池
    filtered_pool = strategy.filter_stock_pool(mock_stocks, datetime.now())
    print(f"\n📌 Step 1 - 股票池过滤后: {len(filtered_pool)} 只")
    for s in filtered_pool:
        print(f"   {s['symbol']} {s['name']}")
    
    # Step 2: 成长因子筛选
    growth_stocks = strategy.filter_by_growth(filtered_pool, mock_financial)
    print(f"\n📌 Step 2 - 成长因子筛选后: {len(growth_stocks)} 只")
    for s in growth_stocks:
        print(f"   {s['symbol']} {s['name']} - 营收同比: {s['rev_yoy']:.1f}%, 利润同比: {s['profit_yoy']:.1f}%")
    
    # Step 3: 市值排序选股
    selected = strategy.rank_by_market_cap(growth_stocks, mock_market)
    print(f"\n📌 Step 3 - 最终选股: {len(selected)} 只")
    print("-" * 40)
    
    for i, s in enumerate(selected, 1):
        print(f"   {i}. {s['symbol']} {s['name']}")
        print(f"      流通市值: {s['market_cap_yi']:.1f} 亿")
        print(f"      营收同比: {s['rev_yoy']:.1f}%")
        print(f"      利润同比: {s['profit_yoy']:.1f}%")
        print()
    
    print("=" * 60)
    print("✅ Demo 完成！")
    print("=" * 60)
    
    return selected


def demo_custom_config():
    """演示自定义配置"""
    
    print("\n" + "=" * 60)
    print("🔧 自定义配置示例")
    print("=" * 60)
    
    # 创建自定义配置
    config = SmallCapConfig(
        # 股票过滤器
        stock_filter=StockFilter(
            exclude_st=True,
            exclude_new_stocks=True,
            new_stock_days=180,       # 改为180天
            exclude_kcb=True,
            exclude_cyb=False,        # 允许创业板
            exclude_bj=False,         # 允许北交所
        ),
        # 成长因子配置
        growth_filter=GrowthFilter(
            use_relative_rank=True,
            revenue_percentile=0.6,   # 前40%（更严格）
            profit_percentile=0.6,
        ),
        # 选股配置
        top_n=20,
        use_float_value=True,
        max_market_cap=50,            # 最大50亿
        min_market_cap=5,             # 最小5亿
    )
    
    strategy = SmallCapGrowthStrategy(config)
    
    print("\n📋 自定义策略配置：")
    pprint(strategy.get_strategy_info())


if __name__ == "__main__":
    # 运行 Demo
    demo_with_mock_data()
    demo_custom_config()
