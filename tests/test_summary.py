"""答完一轮那句「总结」:从整段回复里抠第一句(纯逻辑,不用 Qt)。"""
import pytest

from claude_cockpit import summary


def test_takes_the_first_sentence_with_its_punctuation():
    got = summary.first_sentence("改完了。接下来还要跑一遍测试。")
    assert got == "改完了。"          # 终止符留着,不然读起来像被掐断


def test_newline_ends_a_sentence():
    """回复经常是「一行结论 + 下面列几条」,首行本身就是那句话,不等句号。"""
    assert summary.first_sentence("已修好登录超时\n- 改了重试次数\n- 补了用例") \
        == "已修好登录超时"


def test_code_fence_is_dropped():
    """代码块常紧跟在第一段后面,不丢的话第一句会变成一行代码。"""
    text = "```python\nprint('hi')\n```\n改完了,顺手补了用例。"
    assert summary.first_sentence(text) == "改完了,顺手补了用例。"


def test_unclosed_fence_swallows_the_rest():
    assert summary.first_sentence("```\nprint('hi')") == ""


def test_markdown_markers_are_stripped():
    assert summary.first_sentence("## **改完了**") == "改完了"
    assert summary.first_sentence("- 第一条:改完了") == "第一条:改完了"


def test_english_period_does_not_cut():
    """`3.5` / 文件名里到处是点,按它断句会断在半截。"""
    assert summary.first_sentence("升级到 3.5 之后不再报错") == "升级到 3.5 之后不再报错"


def test_inline_code_keeps_its_content():
    assert summary.first_sentence("`say()` 现在可以钉住了") == "say() 现在可以钉住了"


@pytest.mark.parametrize("bad", ["", None, "   \n\n  ", "```\n```"])
def test_nothing_to_say(bad):
    assert summary.first_sentence(bad) == ""


def test_long_sentence_is_capped():
    got = summary.first_sentence("啊" * 300)
    assert len(got) == summary.MAX + 1 and got.endswith("…")
