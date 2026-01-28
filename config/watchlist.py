"""
自选股列表
"""

# 美股科技股
US_TECH = [
    "AAPL.US",   # 苹果
    "MSFT.US",   # 微软
    "GOOGL.US",  # 谷歌
    "AMZN.US",   # 亚马逊
    "NVDA.US",   # 英伟达
    "META.US",   # Meta
    "TSLA.US",   # 特斯拉
    "AMD.US",    # AMD
    "NFLX.US",   # Netflix
    "CRM.US",    # Salesforce
]

# 美股 AI 概念
US_AI = [
    "NVDA.US",   # 英伟达
    "AMD.US",    # AMD
    "MSFT.US",   # 微软 (OpenAI)
    "GOOGL.US",  # 谷歌 (Gemini)
    "META.US",   # Meta (LLaMA)
    "PLTR.US",   # Palantir
    "AI.US",     # C3.ai
    "PATH.US",   # UiPath
]

# 港股科技
HK_TECH = [
    "0700.HK",   # 腾讯
    "9988.HK",   # 阿里巴巴
    "9999.HK",   # 网易
    "3690.HK",   # 美团
    "9618.HK",   # 京东
    "9888.HK",   # 百度
    "1810.HK",   # 小米
]

# 默认监控列表
DEFAULT_WATCHLIST = US_TECH + US_AI[:3]

def get_watchlist(category: str = "default") -> list:
    """获取自选股列表"""
    watchlists = {
        "default": DEFAULT_WATCHLIST,
        "us_tech": US_TECH,
        "us_ai": US_AI,
        "hk_tech": HK_TECH,
        "all": list(set(US_TECH + US_AI + HK_TECH)),
    }
    return watchlists.get(category, DEFAULT_WATCHLIST)
