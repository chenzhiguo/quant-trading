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
    "TSM.US",    # 台积电 (AI芯片制造)
    "AVGO.US",   # 博通 (AI网络芯片)
    "SMCI.US",   # Super Micro (AI服务器)
    "ARM.US",    # ARM Holdings
]

# 美股核心护城河 (AI/互联网/软件) - 财务稳健 + 持续成长
US_CORE_MOAT = [
    # --- 基础设施 (铲子股) ---
    "NVDA.US",   # 英伟达: GPU 垄断 + CUDA 生态 (绝对护城河)
    "TSM.US",    # 台积电: 先进封装垄断 (无可替代)
    "AVGO.US",   # 博通: 顶级网络芯片 + 软件高毛利 (现金牛)
    "ASML.US",   # 阿斯麦: 光刻机垄断 (人类工业皇冠)
    
    # --- 云计算与平台 (地主) ---
    "MSFT.US",   # 微软: Azure + Office + Copilot (最强B端生态)
    "GOOGL.US",  # 谷歌: 搜索垄断 + TPU/DeepMind (最强AI底蕴)
    "AMZN.US",   # 亚马逊: AWS 云龙头 + 电商物流壁垒
    "META.US",   # Meta: 30亿用户社交图谱 + 广告印钞机
    
    # --- 关键软件 (SaaS 粘性) ---
    "ORCL.US",   # 甲骨文: 数据库粘性 + 云增速 (老树发新芽)
    "CRM.US",    # Salesforce: 客户关系数据垄断 (Agentforce)
    "ADBE.US",   # Adobe: 创意工作流垄断 (Firefly AI)
    "NOW.US",    # ServiceNow: 企业数字化工作流 (极高留存率)
    "PLTR.US",   # Palantir: 军工/企业操作系统 (独特护城河)
    
    # --- 网络安全 (刚需) ---
    "PANW.US",   # Palo Alto: 网安平台化龙头
]

# 大师共识精选 (Terry Smith + Pat Dorsey + Will Danoff)
# 筛选标准: 高ROCE + 高转换成本 + 持续成长
US_CONSENSUS = [
    "MSFT.US",   # 微软 (全票通过: 质量+护城河+成长)
    "CDNS.US",   # Cadence (EDA软件双寡头, 芯片行业的收税人)
    "SNPS.US",   # Synopsys (EDA软件双寡头, 极高转换成本)
    "ADBE.US",   # Adobe (创意垄断, 极佳的SaaS模式)
    "NOW.US",    # ServiceNow (极高客户留存率, IT基础设施)
    "GOOGL.US",  # 谷歌 (搜索网络效应, 现金流充沛)
    "CRM.US",    # Salesforce (企业数据核心)
    "ANET.US",   # Arista (数据中心网络, 软硬结合壁垒)
    "INTU.US",   # Intuit (税务软件垄断, 美国中小企业刚需)
]

# 港股科技 (暂时禁用)
HK_TECH = [
    # "0700.HK",   # 腾讯
    # "9988.HK",   # 阿里巴巴
    # "9999.HK",   # 网易
    # "3690.HK",   # 美团
    # "9618.HK",   # 京东
    # "9888.HK",   # 百度
    # "1810.HK",   # 小米
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

# 港股互联网（扩展）(暂时禁用)
HK_INTERNET = [
    # "0700.HK",   # 腾讯
    # "9988.HK",   # 阿里巴巴
    # "9999.HK",   # 网易
    # "3690.HK",   # 美团
    # "9618.HK",   # 京东
    # "9888.HK",   # 百度
    # "1810.HK",   # 小米
    # "9866.HK",   # 蔚来
    # "9868.HK",   # 小鹏汽车
    # "2015.HK",   # 理想汽车
    # "9626.HK",   # 哔哩哔哩
    # "1024.HK",   # 快手
    # "2382.HK",   # 舜宇光学
    # "0241.HK",   # 阿里健康
    # "6060.HK",   # 众安在线
    # "1833.HK",   # 平安好医生
    # "9961.HK",   # 携程
    # "9698.HK",   # 万国数据
]

# 个股监控（扩展分析范围）
MONITOR_STOCKS = [
    "ORCL.US",   # 甲骨文 Oracle
    "NET.US",    # CloudFlare
    "SAP.US",    # SAP
    "FIG.US",    # Figma (请确认代码有效性)
    "INTC.US",   # 英特尔 Intel
    "ARM.US",    # ARM Holdings
    "AVGO.US",   # 博通 Broadcom
    "MU.US",     # 美光科技 Micron
    "WMT.US",    # 沃尔玛 Walmart
    "GD.US",     # 通用动力 General Dynamics
    "TSM.US",    # 台积电 TSMC ADR
    "RDDT.US",   # Reddit
    "QCOM.US",   # 高通 Qualcomm
    "WDC.US",    # 西部数据 (含Sandisk)
    "STX.US",    # 希捷 Seagate
    "NKE.US",    # 耐克 Nike
]

# 杠杆ETF（高波动交易）
LEVERAGED_ETF = [
    "QQQ.US",    # 纳斯达克100指数ETF
    "YANG.US",   # 富时中国3倍做空ETF
    "FXP.US",    # 2倍做空富时中国50 ETF
    "TQQQ.US",   # 3倍做多纳指ETF
    "SQQQ.US",   # 3倍做空纳指ETF
    "SOXL.US",   # 半导体3倍做多ETF
    "SOXS.US",   # 半导体3倍做空ETF
    "GLL.US",    # 2倍做空黄金ETF
    "TSLL.US",   # 1.5倍做多特斯拉ETF
]

# 默认监控列表
DEFAULT_WATCHLIST = US_TECH + US_AI[:3]

# 优化后的精选列表 (剔除杠杆ETF和极度不稳定的个股)
OPTIMIZED_BATCH = [
    # 表现极佳的趋势股
    "MU.US", "PLTR.US", "AVGO.US", "STX.US", "NVDA.US", "META.US", "NET.US",
    # 稳健大盘股
    "MSFT.US", "GOOGL.US", "QCOM.US", "WMT.US", "TSM.US", "INTU.US",
    # 表现良好的中概股 (波段交易)
    "BABA.US", "JD.US", "TCOM.US", "NTES.US",
    # 潜力股 (需宽止损)
    "TSLA.US", "AMD.US", "XPEV.US", "LI.US", "CRM.US"
]

def get_watchlist(category: str = "default") -> list:
    """获取自选股列表"""
    watchlists = {
        "default": DEFAULT_WATCHLIST,
        "optimized": OPTIMIZED_BATCH,  # 新增: 优化后的列表
        "us_tech": US_TECH,
        "us_ai": US_AI,
        "us_moat": US_CORE_MOAT,
        "us_consensus": US_CONSENSUS,  # 新增: 大师共识
        "hk_tech": HK_TECH,
        "hk_internet": HK_INTERNET,
        "cn_adr": CN_ADR,
        "monitor": MONITOR_STOCKS,
        "etf": LEVERAGED_ETF,
        "china": list(set(HK_INTERNET + CN_ADR)),  # 所有中国公司
        "all": list(set(US_TECH + US_AI + US_CORE_MOAT + US_CONSENSUS + HK_INTERNET + CN_ADR + MONITOR_STOCKS + LEVERAGED_ETF)),
    }
    return watchlists.get(category, DEFAULT_WATCHLIST)


def list_categories() -> dict:
    """列出所有分类及股票数量"""
    return {
        "default": f"默认列表 ({len(DEFAULT_WATCHLIST)}只)",
        "us_tech": f"美股科技 ({len(US_TECH)}只)",
        "us_ai": f"美股AI概念 ({len(US_AI)}只)",
        "us_moat": f"核心护城河 ({len(US_CORE_MOAT)}只)",
        "us_consensus": f"大师共识 ({len(US_CONSENSUS)}只)",
        "hk_tech": f"港股科技 ({len(HK_TECH)}只)",
        "hk_internet": f"港股互联网 ({len(HK_INTERNET)}只)",
        "cn_adr": f"中概股ADR ({len(CN_ADR)}只)",
        "monitor": f"个股监控 ({len(MONITOR_STOCKS)}只)",
        "etf": f"杠杆ETF ({len(LEVERAGED_ETF)}只)",
        "china": f"所有中国公司 ({len(set(HK_INTERNET + CN_ADR))}只)",
        "all": f"全部 ({len(set(US_TECH + US_AI + HK_INTERNET + CN_ADR + MONITOR_STOCKS + LEVERAGED_ETF))}只)",
    }
