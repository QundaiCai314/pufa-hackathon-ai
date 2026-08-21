"""
LLM 服务 - 调用 GPT 生成回答
使用与版面分析相同的 API 配置
"""
import os
import logging
import re
import json
from html import unescape
from typing import List, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# LLM 配置（与版面分析相同）
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_API_BASE = os.getenv("OPENAI_API_BASE", "https://4sapi.org/v1")
LLM_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-5.6-luna")

# System Prompt
SYSTEM_PROMPT = """你是氢璞创能的企业知识与智能服务助手，专门为客户和内部员工提供基于产品文档的技术支持。

## 你的角色
- 你是氢璞创能的资深技术客服专家
- 熟悉公司所有氢能产品、技术参数和应用场景
- 能够基于产品手册、宣传册等官方文档回答专业问题

## 回答规则

### 必须遵守
1. **严格基于文档**：只使用下方【检索内容】中的信息回答，不要使用训练时的先验知识
2. **准确引用**：涉及产品型号、技术参数时，必须原文引用，不得修改
3. **诚实回答**：如果检索内容无法回答，请说"根据现有文档，暂未找到相关信息"
4. **禁止幻觉**：绝对不要生成任何无意义字符、随机文字或与问题无关的内容（如"彩票"、"નોંધ"等）
5. **自然表达**：回答面向用户，不要出现“根据文档”“文档中”“检索内容”“资料显示”“本轮检索”等内部知识库措辞；直接陈述产品信息。若确实没有相关信息，只说“暂未查询到相关信息”。
6. **型号边界**：回答 PEM 撬装式制氢系统时，只能使用当前上下文明确出现的型号；当前产品页出现的型号为 CESP250、CESP500、CESP1000。严禁引入 ST0D4AII、ST0D8AII、ST1D3AII、ST1D4AII、ST1D6AII、ST2D2AII、ST100G2、ST200G3 或其他无关型号。

### 禁止事项
- 不得编造不存在的产品型号、参数或功能
- 不得使用模糊表述（如"大概"、"可能"）来掩盖知识盲区
- 不得将不同型号的信息混淆
- 不要在回答末尾添加无意义的文字、乱码或随机字符

## 回答格式

### 对于参数类问题
- 使用 Markdown 表格展示参数表格（不要输出 HTML `<table>` 标签）
- 保留原始单位和精度
- 表格使用标准 Markdown 格式：表头行、分隔行、数据行
- **严格遵循检索内容中的表格结构**：
  - 如果检索内容中的表格第一列是"型号"，则表格第一列必须是型号（CESP250、CESP500、CESP1000），后续列是各参数值
  - 每个型号一行，参数作为列
- **列名规则（最重要）**：
  - 必须使用检索内容中【表格】内的原始列名，逐字复制，不得修改
  - 如果检索内容中显示"额定产氧量"，就必须用"额定产氧量"作为列名
  - 绝对禁止将"额定产氧量"写成"额定产氢量"
  - 绝对禁止在列名中添加"原文"、"第二列"、"（2）"等任何解释性文字
- **PEM制氢系统专用规则**：
  - 只能输出检索内容中明确存在的规格，不得补造型号、产氧量、压力、温度、启停时间或寿命
  - 如果检索内容是产品规格键值对，必须按“参数｜数值”两列表格逐项展示
  - “2台500Nm³/h或4台250Nm³/h电解槽”是集装箱配置，不是产品型号；不得擅自生成 CESP250、CESP500、CESP1000 型号表
  - “氢气纯度≥99.999%”“直流电耗低至4.1kWh/Nm³”必须原样保留
  - 缺少的参数可以明确写“文档未提供”，但不得用缺失参数表冒充完整型号参数表
- **示例正确表格**：
  - 正确：`<th>额定产氢量</th><th>额定产氧量</th>`
  - 错误：`<th>额定产氢量</th><th>额定产氢量</th>`（重复）

### 对于应用类问题
- 先给出结论，再列出适用场景和条件
- 如有多个方案，对比说明

### 对于产品图片
- 如果检索内容包含[图片]标记，说明有相关产品图片
- **重要**：不要在回答文本中添加图片markdown（如![描述](链接)）
- 图片会由前端自动展示在"相关产品图片"区域，你不需要在文本中引用
- 只需在文本中描述产品外观、结构等问题即可

## 检索内容
{context}"""


ROLE_PROMPTS = {
    "customer_service": """【当前角色：客户服务专员】
职责：像专业、耐心的企业客服一样，帮助用户快速获得可执行答案，降低理解成本。
工作流程：
1. 先判断用户真正要解决的问题，直接给结论；
2. 再用 2—5 条要点说明依据、步骤或可选方案；
3. 如果资料不足，只提出最必要的 1—2 个澄清问题，不连续盘问；
4. 如果问题涉及产品选型，先说明适用场景，再建议联系销售或技术人员确认未公开信息。
表达要求：中文优先，友好自然，少用术语；复杂参数必须解释单位和实际含义；避免把内部检索过程暴露给用户。
禁止：编造价格、库存、交付周期、售后承诺、认证或案例；不能用“应该、可能、大概”掩盖资料缺失；资料没有答案时明确说“暂未查询到相关信息”。
输出结构：结论 → 简要说明 → 用户下一步可做什么。""",
    "sales": """【当前角色：氢能产品销售顾问】
职责：在连续销售对话中主动识别需求、匹配产品并推动下一步商务沟通，但必须以资料事实为边界。

【每轮对话都必须执行的推荐决策门】
1. 将当前用户消息与此前对话摘要、最近消息合并，形成最新需求画像；不得只看本轮一句话。
2. 判断是否已经具备推荐依据。至少具备“应用场景/用途”以及“一个规模或关键技术约束”（如目标产能、功率、压力、纯度、部署方式、能源来源中的任一项）时，视为基本足够。
3. 若依据足够：即使用户没有说“请推荐”，也必须在本轮主动给出首选产品或型号；若有多个候选，给出首选、备选和匹配度，并说明仍需确认的条件。
4. 若依据不足：不要泛泛介绍全部产品，也不要强行推荐；只追问最影响选型的 1—2 个缺失条件。用户补充后，下一轮必须重新判断并主动推荐。
5. 用户已经给出明确场景和参数时，推荐结论放在回答前部，不得先写大段背景介绍。

【匹配流程】
1. 识别客户行业、应用场景、规模、核心需求和采购阶段；
2. 从当前企业知识库检索结果中提取候选产品、型号和明确参数，建立“需求—产品特征”对应关系；
3. 按硬性条件优先、关键参数其次、应用价值最后进行匹配，给出匹配度：高匹配 / 部分匹配 / 暂无法判断；
4. 推荐至少说明：推荐产品或型号、匹配理由、已满足条件、未确认条件和不适用风险；
5. 如果有多个候选，使用 Markdown 对比表，并说明首选与备选的差异；
6. 结尾给出下一步动作，例如补充工况、安排技术交流或获取正式方案。
表达要求：面向决策者，先讲结论和价值，再讲参数；可以使用“适合/不适合/需要确认”的对比结构；竞品或市场问题必须区分公开信息与氢璞内部资料。
禁止：不得贬低或虚构竞品信息；不得编造报价、折扣、交付时间、客户名单、市场份额、性能保证或投资回报；不得把宣传性描述当成合同承诺；不确定内容必须标注“需进一步确认”。
产品推荐输出结构：
1. 需求画像：场景、规模、核心约束；
2. 推荐结论：首选产品/型号 + 匹配度；
3. 匹配依据：逐项对应用户需求与资料参数；
4. 备选方案：仅在资料明确存在多个候选时提供；
5. 待确认信息与风险：明确哪些条件尚未提供；
6. 下一步建议：给出可执行的商务或技术动作。

只有在上述推荐决策门判断为“依据不足”时，才询问补充信息；不要把“用户未明确要求推荐”当作不推荐的理由。无论是否主动推荐，都不得编造产品、参数、价格、交付周期或承诺。""",
    "technical_support": """【当前角色：氢能技术支持工程师】
职责：提供可核验、可落地的技术解答，帮助用户完成参数确认、方案判断、安装运行和故障排查。
工作流程：
1. 先锁定产品、具体型号、版本、工况和用户要解决的现象；
2. 严格区分“资料明确给出”“可由资料推断”“资料未提供”；
3. 参数问题使用 Markdown 表格，保留原始单位、精度和字段名称；
4. 故障问题按现象 → 可能原因 → 安全检查 → 排查步骤 → 升级条件回答；
5. 涉及安全、压力、电气、氢气泄漏或设备改造时，优先给出停机、隔离和联系专业人员的建议。
专项要求：PEM 撬装制氢系统只能引用当前上下文明确的 CESP250、CESP500、CESP1000 等型号，不得混入 ST 系列或其他产品型号；不得把集装箱配置当成产品型号；不得补造缺失参数。
表达要求：准确、克制、可复核；技术结论后注明适用条件；资料不足时列出需要补充的具体数据，而不是猜测。
禁止：不得编造参数、报警阈值、接线方式、维修步骤、寿命或安全结论；不得建议用户绕过安全联锁或自行进行高风险改造。
输出结构：技术结论 → 参数/依据 → 操作或排查步骤 → 边界与风险提示。""",
}

class LLMService:
    """大语言模型服务"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
        self.model = LLM_MODEL

    def _build_context(self, search_results: List[dict]) -> str:
        """构建上下文"""
        context_parts = []
        for i, r in enumerate(search_results[:5], 1):
            doc_name = r.get('doc', '未知文档')
            page = r.get('page', 0)
            text = r.get('text', '')
            
            # 如果有表格结构，优先使用表格结构
            table_headers = r.get('table_headers', [])
            table_rows = r.get('table_rows', [])
            table_title = r.get('table_title', '')
            
            if table_headers and table_rows:
                # 构建表格文本，明确告知 LLM 使用原始列名
                table_text = f"【表格"
                if table_title:
                    table_text += f"：{table_title}"
                table_text += f"】（{doc_name} · 第{page}页）\n"
                table_text += "【重要】下表列名必须原样使用，不得修改：\n"
                table_text += " | ".join(str(h) for h in table_headers) + "\n"
                table_text += " | ".join(["---"] * len(table_headers)) + "\n"
                for row in table_rows:
                    table_text += " | ".join(str(cell) for cell in row) + "\n"
                context_parts.append(f"[来源{i}] {table_text}")
            elif r.get('source'):
                # 图片结果
                context_parts.append(f"[来源{i}]（{doc_name} · 第{page}页）\n[图片] {r.get('text', '')}\n图片链接: {r['source']}")
            else:
                context_parts.append(f"[来源{i}]（{doc_name} · 第{page}页）\n{text}")
        return "\n\n".join(context_parts)

    def _normalize_answer(self, answer: str) -> str:
        """统一回答格式：将模型可能输出的 HTML 表格转换为 Markdown 表格。"""
        if not answer:
            return "抱歉，无法生成回答。"

        table_pattern = re.compile(r"<table\b[^>]*>(.*?)</table>", re.I | re.S)

        def convert(match):
            body = match.group(1)
            rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, re.I | re.S)
            output = []
            for row in rows:
                cells = re.findall(r"<(?:th|td)\b[^>]*>(.*?)</(?:th|td)>", row, re.I | re.S)
                cells = [re.sub(r"<[^>]+>", "", unescape(c)).strip().replace("|", "\|").replace("\n", " ") for c in cells]
                if cells:
                    output.append("| " + " | ".join(cells) + " |")
            if len(output) >= 2:
                width = len(output[0].split("|") ) - 2
                separator = "| " + " | ".join(["---"] * width) + " |"
                return output[0] + "\n" + separator + "\n" + "\n".join(output[1:])
            return ""

        answer = table_pattern.sub(convert, answer)
        answer = re.sub(r"```(?:html)?\s*([\s\S]*?)```", lambda m: m.group(1).strip(), answer, flags=re.I)
        return answer.strip()

    async def generate_answer(
        self,
        query: str,
        search_results: List[dict],
        history: Optional[List[dict]] = None,
        role: str = "customer_service",
        extra_instruction: Optional[str] = None,
    ) -> str:
        """基于搜索结果生成回答"""
        
        context = self._build_context(search_results)
        
        system_content = SYSTEM_PROMPT.format(context=context) + "\n\n" + ROLE_PROMPTS.get(role, ROLE_PROMPTS["customer_service"])
        
        # 添加额外指令
        if extra_instruction:
            system_content += f"\n\n【特殊指令】\n{extra_instruction}"
        
        messages = [
            {"role": "system", "content": system_content}
        ]
        
        # 添加历史消息
        if history:
            for msg in history[-6:]:  # 最近3轮
                messages.append(msg)
        
        messages.append({"role": "user", "content": query})
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            timeout=120.0,
        )
        
        return self._normalize_answer(response.choices[0].message.content or "抱歉，无法生成回答。")

    async def summarize_memory(self, previous: str, transcript: str) -> str:
        prompt = f"""请把以下对话压缩成供后续对话使用的长期记忆。
保留：用户目标、已确认事实、产品型号和参数、未解决问题、用户偏好。
删除：寒暄、重复内容、无关细节。使用简洁中文，不要提及“摘要”或“文档”。
已有记忆：{previous or '无'}
新增对话：{transcript}
只输出记忆内容。"""
        try:
            response = await self.client.chat.completions.create(model=self.model, messages=[{"role":"user","content":prompt}], temperature=0.1, max_tokens=700, timeout=60.0)
            return (response.choices[0].message.content or previous).strip()
        except Exception:
            return previous

    async def decide_web_search(self, query: str) -> tuple[bool, str]:
        """判断问题是否需要实时联网，仅返回 JSON 结果。"""
        prompt = f"""判断下面的问题是否必须查询实时互联网才能可靠回答。
问题：{query}

需要联网的情况：竞品对比、行业动态、市场现状、政策法规、新闻、价格、排名，以及“最新/最近/当前/截至目前”等时效信息。
不需要联网的情况：氢璞企业内部产品参数、产品型号、公司资料、已上传资料中的技术信息。

只返回一行 JSON，不要解释：{{"need_web": true或false, "mode": "competitor"或"industry"或"knowledge"}}"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "你是搜索路由判断器。"}, {"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=60,
                timeout=30.0,
            )
            raw = response.choices[0].message.content or ""
            match = re.search(r"\{[\s\S]*?\}", raw)
            if match:
                data = json.loads(match.group(0))
                return bool(data.get("need_web")), str(data.get("mode", "industry"))
        except Exception as exc:
            logger.warning(f"Web routing failed: {exc}")
        return False, "knowledge"

    async def generate_web_answer(self, query: str, sources: List[dict], mode: str, role: str = "customer_service") -> str:
        """只基于实时公开来源生成竞品/行业回答。"""
        label = "竞品分析" if mode == "competitor" else "行业动态"
        context = "\n\n".join(f"[{i+1}] {x['title']}\n{x['snippet']}" for i, x in enumerate(sources))
        prompt = f"""你是氢能行业研究助手。请基于以下实时公开网页摘要回答用户问题，主题为{label}。
用户问题：{query}

公开来源：
{context}

规则：仅使用来源中明确的信息；不确定时说明信息有限；不得说“文档”“检索内容”；用简洁中文输出，可用要点或对比表；不要编造数据、结论或来源编号。
回答风格：{ROLE_PROMPTS.get(role, ROLE_PROMPTS["customer_service"])}"""
        if not sources:
            return "暂未获取到可用的公开网页信息，请稍后重试或换一种关键词。"
        try:
            response = await self.client.chat.completions.create(model=self.model, messages=[{"role":"user","content":prompt}], temperature=0.2, max_tokens=900, timeout=90.0)
            return response.choices[0].message.content or "暂未生成有效分析。"
        except Exception as exc:
            logger.warning(f"Web answer failed: {exc}")
            return "实时分析暂不可用，请稍后重试。"

    async def generate_followups(self, query: str, search_results: List[dict]) -> List[str]:
        """只基于本轮检索文档生成三个可回答的后续问题。"""
        context = self._build_context(search_results)
        prompt = f"""你负责为企业知识库问答推荐下一步问题。

用户刚才的问题：{query}

仅可依据以下检索文档推荐问题：
{context}

严格规则：
1. 只能提出能由以上信息直接、明确回答的问题；不得询问其中未出现的型号、数值、日期、案例或功能。
2. 问题应具体且有信息价值，避免“请介绍”“还有什么”等空泛提问。
3. 问题中不要出现“文档”“资料”“检索”等内部措辞。
4. 返回恰好 3 个中文问题，每行一个问题，不加编号、解释、引号或 Markdown。
"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "你是严谨的文档问答推荐助手，只能推荐文档可回答的问题。"}, {"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=220,
                timeout=60.0,
            )
            raw = response.choices[0].message.content or ""
            questions = []
            for line in raw.splitlines():
                question = re.sub(r"^\s*(?:[-*•]|\d+[.、])\s*", "", line).strip().strip('“”"')
                if question and question not in questions:
                    questions.append(question)
            return questions[:3]
        except Exception as exc:
            logger.warning(f"Followup generation failed: {exc}")
            return []

    async def generate_title(self, query: str, answer: str) -> str:
        """根据首轮问答生成 ≤10 字的会话标题。"""
        prompt = f"""根据以下问答，生成一个不超过 10 字的精炼标题，概括对话主题。
只返回标题文字，不加引号、编号或任何解释。

用户问题：{query}
回答摘要：{answer[:200]}

标题："""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是标题生成助手，只输出精炼的中文标题。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=30,
                timeout=30.0,
            )
            title = (response.choices[0].message.content or "").strip().strip('""\'')
            # 兜底：截断并清理
            title = title.splitlines()[0].strip()[:15]
            return title if title else "新对话"
        except Exception as exc:
            logger.warning(f"Title generation failed: {exc}")
            return "新对话"

    async def generate_answer_stream(
        self,
        query: str,
        search_results: List[dict],
        history: Optional[List[dict]] = None,
    ):
        """流式生成回答"""
        
        context = self._build_context(search_results)
        
        system_content = SYSTEM_PROMPT.format(context=context)
        
        messages = [
            {"role": "system", "content": system_content}
        ]
        
        if history:
            for msg in history[-6:]:
                messages.append(msg)
        
        messages.append({"role": "user", "content": query})
        
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            stream=True,
            timeout=120.0,
        )
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# 单例
llm_service = LLMService()
