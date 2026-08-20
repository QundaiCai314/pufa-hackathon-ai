import json
import re
from typing import Any

WEIGHTS = {
    "project": 20, "scale": 20, "timeline": 15, "budget": 15,
    "technical": 15, "decision": 10, "contact": 5,
}

def _signals(text: str) -> dict[str, bool]:
    return {
        "project": bool(re.search(r"项目|建设|落地|示范|采购|招标", text)),
        "scale": bool(re.search(r"\d+(?:\.\d+)?\s*(?:Nm[³3]|kW|MW|吨|台|套)|产能|规模|功率", text, re.I)),
        "timeline": bool(re.search(r"本月|下月|今年|明年|季度|\d+个?月|时间节点|交付|上线", text)),
        "budget": bool(re.search(r"预算|报价|价格|成本|投资|资金|万元|亿元", text)),
        "technical": bool(re.search(r"压力|纯度|温度|效率|电耗|负载|型号|参数|PEM|AEM|配置", text, re.I)),
        "decision": bool(re.search(r"采购|购买|订购|方案|合同|报价|招标|尽快|安排会议|技术交流", text)),
        "contact": bool(re.search(r"电话|手机|微信|邮箱|联系我|联系方式", text)),
    }

def score_lead(text: str) -> dict[str, Any]:
    signals = _signals(text)
    score = min(100, sum(WEIGHTS[k] for k, v in signals.items() if v))
    level = "high" if score >= 70 else ("medium" if score >= 35 else "low")
    return {"score": score, "level": level, "signals": signals}
