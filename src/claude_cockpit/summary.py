"""从 Claude 答完那一轮的整段回复里,抠出**总结性的那句话**(纯逻辑,不 import Qt)。

干嘛用:点工位会朗读这一轮的回复,但语音是线性的——要听完才知道说了什么。所以
同一时刻把**第一句**印在工位的气泡里(和会话间发消息那个气泡同一份画法),让人
一眼看到结论,剩下的交给耳朵。

**只取第一句,不摘要**:Claude 的回复几乎都是「先一句结论、再展开」,取第一句是
免费的总结;真去概括就得再跑一次模型,hook 里跑不起也不该跑。

取法上有几处是踩出来的:
- **代码块整块丢掉**(` ``` ` 围起来的):它常常就在第一段后面,不丢的话第一句会
  变成一行代码。
- **换行也算句子结束**:回复经常是「## 改完了」「- 第一条…」这种,首行本身就是
  那句结论,不等到句号。
- 英文句点**不当终止符**:`3.5` / `tts_stop.py` 里到处是点,按它断会断在半截。
  中文标点(。!?;)才断句——这台机上的回复是中文的。
"""
from __future__ import annotations

import re

MAX = 60                # 气泡最多 5 行、一行十几个字,再长也是省略号,不如早点收
_END = "。!?;！？；"      # 断句用的终止符(英文句点不算,见模块头)


def _strip(text: str) -> str:
    """把 markdown 的记号洗掉,只留能读出来的字。"""
    text = re.sub(r"```.*?```", " ", str(text or ""), flags=re.S)
    text = re.sub(r"```.*", " ", text, flags=re.S)      # 没闭合的围栏:后面整段都别要
    text = re.sub(r"`([^`\n]*)`", r"\1", text)          # 行内代码脱掉反引号,内容留着
    text = re.sub(r"!?\[([^\]\n]*)\]\([^)\n]*\)", r"\1", text)   # 链接只留文字
    text = re.sub(r"^[\s>*#\-+\d.)、]+", "", text, flags=re.M)   # 行首的标题/列表记号
    text = re.sub(r"[*#|]|__", "", text)
    return text


def first_sentence(text: str, limit: int = MAX) -> str:
    """整段回复 → 开头那一句(取不到就空串;空串 = 不冒气泡)。"""
    for line in _strip(text).splitlines():
        line = " ".join(line.split())
        if not line:
            continue
        cut = len(line)
        for i, ch in enumerate(line):
            if ch in _END:
                cut = i + 1                 # 终止符本身留着,不然读起来像被掐断
                break
        s = line[:cut].strip()
        if not s:
            continue
        return s if len(s) <= limit else s[:limit].rstrip() + "…"
    return ""
