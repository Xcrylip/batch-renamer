"""「分段重命名」算子（SegmentRename）的单元测试。

覆盖：
    * 文字区 / 数字区 各三种模式（keep / seq / fixed）的常见组合；
    * 分隔符只在「两区都非空」时才插入；
    * 补零位数 + adaptive（补零后自动省前导零）的两种规则；
    * 字母序号 index_to_letters 的 26 进制进位；
    * 用 generate_plan 真跑一遍，确认 reset 后结果不漂移（连点两次预览一致）。
"""

from batch_renamer.core import generate_plan
from batch_renamer.operations import SegmentRename, format_index, index_to_letters


def _names(files, op):
    """用 generate_plan 跑一遍，按输入顺序返回新文件名列表。"""
    plan = generate_plan(files, [op])
    return [plan.pairs[f] for f in files]


# ---------------- 文字区 + 数字区 的组合 ----------------

def test_letters_and_numbers_seq():
    op = SegmentRename(text_mode="seq", digit_mode="seq", separator="_")
    assert _names(["一.txt", "二.txt", "三.txt"], op) == ["a_1.txt", "b_2.txt", "c_3.txt"]


def test_fixed_text_with_seq_numbers():
    op = SegmentRename(text_mode="fixed", text_fixed="图片",
                       digit_mode="seq", digits=2, adaptive=True)
    assert _names(["x.png", "y.png", "z.png"], op) == ["图片01.png", "图片02.png", "图片03.png"]


def test_keep_both_keeps_original():
    op = SegmentRename(text_mode="keep", digit_mode="keep")
    assert _names(["旅行照片2024.png"], op) == ["旅行照片2024.png"]


def test_digit_keep_uses_original_digits_with_new_text():
    op = SegmentRename(text_mode="seq", digit_mode="keep", separator="-")
    assert _names(["a7.txt", "b8.txt"], op) == ["a-7.txt", "b-8.txt"]


def test_fixed_both():
    op = SegmentRename(text_mode="fixed", text_fixed="IMG",
                       digit_mode="fixed", digit_fixed="001", separator="_")
    assert _names(["a.txt", "b.txt"], op) == ["IMG_001.txt", "IMG_001.txt"]


# ---------------- 分隔符与「空段」 ----------------

def test_no_separator_when_one_part_empty():
    # 数字区是 keep，但原文件名里没有数字 → 数字段为空，不该留下多余分隔符
    op = SegmentRename(text_mode="fixed", text_fixed="P",
                       digit_mode="keep", separator="_")
    assert _names(["abc.png"], op) == ["P.png"]


def test_extension_kept():
    op = SegmentRename(text_mode="seq", digit_mode="seq")
    assert _names(["note.md"], op) == ["a1.md"]


# ---------------- 补零规则 ----------------

def test_format_index_no_padding():
    assert format_index(1, 0, True) == "1"
    assert format_index(10, 0, False) == "10"


def test_format_index_adaptive_fixed_width():
    # adaptive=True：总宽度固定，进位后自动丢掉多余的前导零
    assert format_index(9, 3, True) == "009"
    assert format_index(10, 3, True) == "010"
    assert format_index(100, 3, True) == "100"


def test_format_index_non_adaptive_fixed_zeros():
    # adaptive=False：前导零「个数」固定，进位后位数会变长
    assert format_index(9, 3, False) == "009"
    assert format_index(10, 3, False) == "0010"


# ---------------- 字母进位 ----------------

def test_index_to_letters_carry():
    assert index_to_letters(1) == "a"
    assert index_to_letters(26) == "z"
    assert index_to_letters(27) == "aa"
    assert index_to_letters(28) == "ab"


def test_letters_start_and_step():
    op = SegmentRename(text_mode="seq", text_start=3, text_step=2, digit_mode="seq")
    assert _names(["a.txt", "b.txt", "c.txt"], op) == ["c1.txt", "e2.txt", "g3.txt"]


def test_numbers_start_and_step():
    op = SegmentRename(text_mode="keep", digit_mode="seq", start=10, step=5)
    assert _names(["a.txt", "b.txt"], op) == ["a10.txt", "b15.txt"]


# ---------------- 状态与可重复性 ----------------

def test_plan_is_repeatable():
    files = ["a.txt", "b.txt", "c.txt"]
    op = SegmentRename(text_mode="seq", digit_mode="seq")
    first = _names(files, op)
    second = _names(files, op)
    # generate_plan 会先 reset，连点两次「预览」结果不能漂移
    assert first == second == ["a1.txt", "b2.txt", "c3.txt"]
