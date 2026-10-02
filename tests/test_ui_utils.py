"""UI 参数规整的回归测试。

背景（真机闪退根因，勿删）：
    红米 Note 14 上 App「打开即闪退」，logcat 只看到 hwuiTask 的
    ``Fatal signal 6``（次生现象），真正的死因要 `run-as` 读私有目录里的
    ``files/crash.log`` 才看得到：
        RoundedRectangle.__init__ -> _check_radius
        GraphicException: Invalid radius value, must be list of tuples/numerics
    源头是 ``RoundButton.__init__`` 里 ``[radius]`` 又包了一层，
    传入 ``radius=[dp(18)]`` 时得到 ``[[18.0]]``（嵌套 list）-> Kivy 必炸。
    该异常发生在 ``App.build()`` 期间，CPython 直接结束进程，所以表现成闪退。

本文件的作用：把「半径规整」钉死在 CI 里。
Kivy 在 CI（buildozer 之外的普通 job）装不上，所以规矩逻辑抽到了
``batch_renamer/ui_utils.py``（纯 Python），这里对它做全量覆盖，
并额外做一次「main.py 源码不得再出现危险写法」的静态回归。
"""

import re
from pathlib import Path

import pytest

from batch_renamer.ui_utils import normalize_radius

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_PY = REPO_ROOT / "main.py"


# ---------------- 复刻 Kivy 的校验规则（用于交叉验证） ----------------

def kivy_check_radius(radius):
    """复刻 Kivy 2.3.0 ``RoundedRectangle._check_radius`` 的判定。

    规则：把 radius 当可迭代对象逐个检查元素
      * ``int`` / ``float`` -> 合法
      * ``tuple``            -> 合法（四角写法）
      * 其它（尤其 ``list``）-> 抛 GraphicException

    只用来「交叉验证」normalize_radius 的产出，不参与实现。
    """
    for item in radius:
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            continue
        if isinstance(item, tuple):
            continue
        raise ValueError(
            "Invalid radius value, must be list of tuples/numerics: %r" % (item,)
        )
    return True


def assert_kivy_safe(radius):
    """规整结果必须满足两件事：非空 list、且能过 Kivy 的校验。"""
    assert isinstance(radius, list), "必须是 list，Kivy 不接受其它容器"
    assert radius, "不能为空，空 list 会让 Kivy 回落到默认值"
    assert kivy_check_radius(radius) is True
    return radius


# ---------------- 回归主案：嵌套 list（本次闪退的直接原因） ----------------

def test_nested_single_list_is_flattened():
    """[[18.0]] 是本次真机闪退的元凶，必须被拆成 [18.0]。"""
    assert normalize_radius([[18.0]]) == [18.0]


def test_nested_list_from_dp_is_flattened():
    """模拟真实场景：RoundButton 传 radius=[dp(18)]，又被包一层。"""
    dp18 = float(18)  # 容器里没有 Kivy，dp() 本质上就是个 float
    assert normalize_radius([dp18]) == [18.0]
    assert normalize_radius([[dp18]]) == [18.0]


def test_old_buggy_pattern_would_have_failed():
    """证明「旧写法」确实会被 Kivy 拒绝，说明这个修复是有意义的。"""
    old_style = [18.0]
    buggy = [old_style]  # 旧代码 self._radius = [radius] 干的就是这件事
    assert buggy == [[18.0]]
    with pytest.raises(ValueError):
        kivy_check_radius(buggy)


# ---------------- 各类合法入参 ----------------

def test_plain_number():
    assert normalize_radius(18) == [18.0]
    assert normalize_radius(18.5) == [18.5]
    assert all(isinstance(v, float) for v in normalize_radius(18))


def test_single_element_containers():
    assert normalize_radius([18.0]) == [18.0]
    assert normalize_radius((18.0,)) == [18.0]


def test_four_numerics_passthrough():
    assert normalize_radius([18.0, 18.0, 18.0, 18.0]) == [18.0, 18.0, 18.0, 18.0]


def test_corner_tuples_passthrough():
    """Kivy 的四角 tuple 写法必须原样保留，不能被拆散。"""
    corners = [(18.0, 18.0), (18.0, 18.0)]
    assert normalize_radius(corners) == corners
    assert_kivy_safe(normalize_radius(corners))

    single = [(10.0, 10.0, 10.0, 10.0)]
    assert normalize_radius(single) == single


# ---------------- 非法入参必须兜底，绝不冒泡到 Kivy ----------------

@pytest.mark.parametrize("bad", [
    None,
    True,
    False,
    "18",
    object(),
    {},
    float("nan"),
])
def test_invalid_inputs_fall_back(bad):
    got = normalize_radius(bad)
    assert_kivy_safe(got)
    assert len(got) == 1


def test_empty_and_junk_containers_fall_back():
    assert normalize_radius([]) == [10.0]
    assert normalize_radius([None, "x", []]) == [10.0]
    assert normalize_radius([True, "x"]) == [10.0]


def test_junk_inside_valid_list_is_dropped():
    """混入垃圾时保留可用部分，而不是整体退化成默认值。"""
    assert normalize_radius([18.0, "x", None]) == [18.0]


def test_custom_default():
    assert normalize_radius(None, default=6) == [6.0]
    assert normalize_radius([], default=6.0) == [6.0]
    assert normalize_radius(None, default="bad") == [10.0]


# ---------------- 全量交叉验证：任何输入产出都必须能被 Kivy 接受 ----------------

@pytest.mark.parametrize("raw", [
    None, 0, 1, 18, 18.0, -3, True,
    [], [0], [18.0], [[18.0]], [[[18.0]]],
    [18.0, 18.0, 18.0, 18.0],
    [(18.0, 18.0), (18.0, 18.0)],
    [(10, 10, 10, 10)],
    [(1, 2)], [None], ["x"], [None, 12.0], {"r": 1},
])
def test_every_output_is_kivy_safe(raw):
    assert_kivy_safe(normalize_radius(raw))


# ---------------- 静态回归：main.py 不得再出现危险写法 ----------------

def _code_only(src):
    """去掉文档字符串与注释，避免「解释旧 bug 的文字」被误判成危险代码。"""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    out = []
    for line in src.splitlines():
        if line.lstrip().startswith("#"):
            continue
        pos = line.find("#")
        if pos != -1 and '"' not in line[:pos] and "'" not in line[:pos]:
            line = line[:pos]
        out.append(line)
    return "\n".join(out)


def test_main_py_has_no_nested_radius_literal():
    """main.py 的**代码**里不允许再写 `radius=[dp(N)]`（会与包装逻辑叠加成嵌套 list）。

    注释里允许出现，因为那正是本次 bug 的说明文字。
    """
    src = _code_only(MAIN_PY.read_text(encoding="utf-8"))
    hits = re.findall(r"radius\s*=\s*\[\s*dp\s*\(", src)
    assert hits == [], "发现危险的 radius=[dp(...)] 写法：%r" % (hits,)


def test_main_py_routes_radius_through_normalizer():
    """绘图工具与 RoundButton 都必须走 _norm_radius 兜底。"""
    src = _code_only(MAIN_PY.read_text(encoding="utf-8"))
    assert "from batch_renamer.ui_utils import normalize_radius" in src
    assert "def _norm_radius(" in src
    assert "self._radius = _norm_radius(radius)" in src
    # 定义 1 处 + _draw_round 调用 1 处 + RoundButton.__init__ 调用 1 处（注释已剔除）
    assert src.count("_norm_radius(") == 3, "调用点数量变了，检查是否有分支漏改或漏走兜底"


def test_main_py_keeps_crash_log_fallback():
    """崩溃日志兜底不能删：真机私有目录可写，scoped storage 不一定能读。"""
    src = MAIN_PY.read_text(encoding="utf-8")
    assert "ANDROID_PRIVATE" in src
    assert "def _crash_hook(" in src