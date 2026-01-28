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
    "SMCI.US",   # Super Micro (AI服务器)
    "ARM.US",    # ARM Holdings
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

# 中概股（美股上市的中国公司）
CN_ADR = [
    "BABA.US",   # 阿里巴巴 ADR
    "JD.US",     # 京东 ADR
    "PDD.US",    # 拼多多
    "BIDU.US",   # 百度 ADR
    "NIO.US",    # 蔚来汽车
    "XPEV.US",   # 小鹏汽车
    "LI.US",     # 理想汽车
    "BILI.US",   # 哔哩哔哩
    "TME.US",    # 腾讯音乐
    "NTES.US",   # 网易 ADR
    "BEKE.US",   # 贝壳找房
    "ZTO.US",    # 中通快递
    "VIPS.US",   # 唯品会
    "IQ.US",     # 爱奇艺
    "TCOM.US",   # 携程
]

# 港股互联网（扩展）
HK_INTERNET = [
    "0700.HK",   # 腾讯
    "9988.HK",   # 阿里巴巴
    "9999.HK",   # 网易
    "3690.HK",   # 美团
    "9618.HK",   # 京东
    "9888.HK",   # 百度
    "1810.HK",   # 小米
    "9866.HK",   # 蔚来
    "9868.HK",   # 小鹏汽车
    "2015.HK",   # 理想汽车
    "9626.HK",   # 哔哩哔哩
    "1024.HK",   # 快手
    "2382.HK",   # 舜宇光学
    "0241.HK",   # 阿里健康
    "6060.HK",   # 众安在线
    "1833.HK",   # 平安好医生
    "9961.HK",   # 携程
    "9698.HK",   # 万国数据
]

# A股科技（沪深港通）
A_TECH = [
    "600519.SH",  # 贵州茅台（虽然不是科技，但波动大）
    "300750.SZ",  # 宁德时代
    "002594.SZ",  # 比亚迪
    "000333.SZ",  # 美的集团
    "601318.SH",  # 中国平安
    "600036.SH",  # 招商银行
    "002415.SZ",  # 海康威视
    "300059.SZ",  # 东方财富
    "002475.SZ",  # 立讯精密
    "600900.SH",  # 长江电力
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
        "hk_internet": HK_INTERNET,
        "cn_adr": CN_ADR,
        "a_tech": A_TECH,
        "china": list(set(HK_INTERNET + CN_ADR)),  # 所有中国公司
        "all": list(set(US_TECH + US_AI + HK_INTERNET + CN_ADR)),
    }
    return watchlists.get(category, DEFAULT_WATCHLIST)


def list_categories() -> dict:
    """列出所有分类及股票数量"""
    return {
        "default": f"默认列表 ({len(DEFAULT_WATCHLIST)}只)",
        "us_tech": f"美股科技 ({len(US_TECH)}只)",
        "us_ai": f"美股AI概念 ({len(US_AI)}只)",
        "hk_tech": f"港股科技 ({len(HK_TECH)}只)",
        "hk_internet": f"港股互联网 ({len(HK_INTERNET)}只)",
        "cn_adr": f"中概股ADR ({len(CN_ADR)}只)",
        "a_tech": f"A股科技 ({len(A_TECH)}只)",
        "china": f"所有中国公司 ({len(set(HK_INTERNET + CN_ADR))}只)",
        "all": f"全部 ({len(set(US_TECH + US_AI + HK_INTERNET + CN_ADR))}只)",
    }
