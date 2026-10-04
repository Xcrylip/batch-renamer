# -*- coding: utf-8 -*-
"""Kivy headless UI 冒烟测试（需在 Xvfb 虚拟显示下运行）。

目的：真正建立窗口、构建控件树、跑一次布局、模拟用户点击与填表，
去捕捉「语法编译与单元测试都通过、但真机一打开就闪退/看不见字」
的那一类纯 UI 层错误（属性拼错、控件缺失、布局尺寸为 0、文字被
推出屏幕外等）。

运行方式：
    xvfb-run -a -s "-screen 0 1080x2400x24" python3 /tmp/ui_smoke.py
"""
import os
import sys
import shutil
import tempfile
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.setdefault("KIVY_NO_ARGS", "1")
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)

from kivy.clock import Clock          # noqa: E402
from kivy.core.window import Window   # noqa: E402
from kivy.metrics import dp           # noqa: E402

import main as M  # noqa: E402

PASSED = []
FAILED = []
SCREEN_W, SCREEN_H = 1080, 2400


def check(name, cond, extra=""):
    if cond:
        PASSED.append(name)
        print("[ OK ] %s %s" % (name, extra))
    else:
        FAILED.append(name)
        print("[FAIL] %s %s" % (name, extra))


def safe(name, fn, *a, **kw):
    try:
        r = fn(*a, **kw)
        PASSED.append(name)
        print("[ OK ] %s" % name)
        return r
    except Exception as e:
        FAILED.append(name)
        print("[FAIL] %s -> %r" % (name, e))
        traceback.print_exc()
        return None


def walk(widget):
    """深度遍历控件树。"""
    yield widget
    for child in widget.children:
        yield from walk(child)


def texts_of(root):
    """收集子树里所有非空文字（按钮 text 或 Label text 都算）。"""
    out = []
    for w in walk(root):
        t = getattr(w, "text", None)
        if isinstance(t, str) and t.strip():
            out.append(t)
    return out


def layout_now():
    """强制跑几轮布局，让容器把 size_hint 解析成真实尺寸。"""
    Window.size = (SCREEN_W, SCREEN_H)
    app.root.size = (SCREEN_W, SCREEN_H)
    for _ in range(6):
        app.root.do_layout()
        Clock.tick()


def label_with_text(root, text):
    for w in walk(root):
        if isinstance(w, M.Label) and (w.text or "") == text:
            return w
    return None


def card_of_label(label):
    """从标题 Label 向上找到入口卡片（FloatLayout 层）。"""
    node = label
    while node is not None and not isinstance(node, M.FloatLayout):
        node = node.parent
    return node


# ============ 1. 启动与构建 ============
print("=== 1. 启动 App 并构建界面 ===")
app = M.BatchRenamerApp()
root = safe("BatchRenamerApp.build()", app.build)
check("build() 返回 ScreenManager", isinstance(root, M.ScreenManager))
app.root = root
check("首页已创建", getattr(app, "home", None) is not None)
safe("首次布局", layout_now)

HOME_TEXTS = texts_of(app.home)
print("    首页可见文字:", HOME_TEXTS)

ENTRIES = [
    ("加前/后缀", M.PrefixSuffixScreen),
    ("查找替换", M.ReplaceScreen),
    ("插入序号", M.IndexScreen),
    ("分段重命名", M.SegmentRenameScreen),
]

# ============ 2. 首页入口：文案 + 几何（防「按钮无字」回归） ============
print("=== 2. 首页入口卡片体检 ===")
entry_cards = {}
for title, cls in ENTRIES:
    check("首页有入口文案「%s」" % title, title in HOME_TEXTS)
    lbl = label_with_text(app.home, title)
    check("能找到「%s」标题 Label" % title, lbl is not None)
    if lbl is None:
        continue
    card = card_of_label(lbl)
    check("「%s」标题有祖先卡片层" % title, card is not None)
    if card is None:
        continue
    entry_cards[title] = (card, lbl)

    # 卡片尺寸：应为 78dp 高、屏宽减去两侧 16dp 内边距
    check("「%s」卡片高度=78dp" % title, abs(card.height - dp(78)) < 1.5,
          "height=%.1f" % card.height)
    check("「%s」卡片宽度≈屏宽-32dp" % title,
          abs(card.width - (SCREEN_W - 2 * dp(16))) < 2.5,
          "width=%.1f 期望=%.1f" % (card.width, SCREEN_W - 2 * dp(16)))

    layers = [c for c in card.children]
    btn = next((c for c in layers if isinstance(c, M.RoundButton)), None)
    inner = next((c for c in layers
                  if isinstance(c, M.BoxLayout) and c is not btn), None)
    check("「%s」有背景按钮层" % title, btn is not None)
    check("「%s」有文字层" % title, inner is not None)
    if btn is not None:
        check("「%s」背景层铺满卡片" % title,
              abs(btn.width - card.width) < 1.5 and abs(btn.height - card.height) < 1.5,
              "btn=%.1fx%.1f" % (btn.width, btn.height))
    if inner is not None:
        check("「%s」文字层铺满卡片（size_hint 被解析）" % title,
              abs(inner.width - card.width) < 1.5 and abs(inner.height - card.height) < 1.5,
              "inner=%.1fx%.1f" % (inner.width, inner.height))

    # 最关键的回归点：标题文字必须落在卡片矩形内（老 bug 是被推到屏幕外）
    check("「%s」标题 Label 有非零尺寸" % title,
          lbl.width > 1 and lbl.height > 1,
          "label=%.1fx%.1f" % (lbl.width, lbl.height))
    lx, ly = lbl.to_window(lbl.x, lbl.y)
    cx, cy = card.to_window(card.x, card.y)
    inside = (lx >= cx - 2 and lx <= cx + card.width + 2 and
              ly >= cy - 2 and ly <= cy + card.height + 2)
    check("「%s」标题落在卡片范围内（不会看不见）" % title, inside,
          "label@(%.0f,%.0f) card@(%.0f,%.0f)+%.0fx%.0f"
          % (lx, ly, cx, cy, card.width, card.height))
    onscreen = (0 <= lx <= SCREEN_W and 0 <= ly <= SCREEN_H)
    check("「%s」标题在屏幕内" % title, onscreen, "(%.0f,%.0f)" % (lx, ly))

# ============ 3. 点击首页入口切页 ============
print("=== 3. 首页入口点击切页 ===")
for title, cls in ENTRIES:
    pair = entry_cards.get(title)
    if pair is None:
        continue
    card, lbl = pair
    btn = next((c for c in card.children if isinstance(c, M.RoundButton)), None)
    if btn is None:
        continue
    safe("点击「%s」不抛异常" % title, btn.dispatch, "on_release")
    check("点击「%s」切到 %s" % (title, cls.__name__),
          app.sm.current == cls.__name__, "当前=%s" % app.sm.current)
    page = app._screens.get(cls)
    check("%s 控件树非空" % cls.__name__,
          page is not None and len(list(walk(page))) > 5)
    app.go_home()
    layout_now()
    check("回到首页", app.sm.current == "home")

# ============ 4. 分段页控件契约 ============
print("=== 4. 分段重命名页控件契约 ===")
seg = app._screens.get(M.SegmentRenameScreen)
check("分段页实例存在", seg is not None)
seg = safe("打开分段页", app.go_screen, M.SegmentRenameScreen) or seg
layout_now()

REQUIRED_ATTRS = [
    "text_seg", "digit_seg", "text_start_input", "text_step_input",
    "text_fixed_input", "start_input", "step_input", "digits_input",
    "digit_fixed_input", "adaptive_switch", "sep_input", "sort_seg",
    "result_label",
]
for attr in REQUIRED_ATTRS:
    check("分段页存在控件 %s" % attr, hasattr(seg, attr))

# 每个功能页都应有预览 / 执行 / 返回
for title, cls in ENTRIES:
    page = app._screens[cls]
    ts = texts_of(page)
    check("%s 有「预览」按钮" % cls.__name__, any("预览" in t for t in ts))
    check("%s 有「执行」按钮" % cls.__name__, any("执行" in t for t in ts))
    backs = [w for w in walk(page)
             if isinstance(w, M.RoundButton)
             and getattr(w, "_icon_line", None) is not None]
    check("%s 有返回键(‹)" % cls.__name__, len(backs) >= 1)

# 分段页的两个分段选择器应真的被布局出尺寸
check("文字区分段控件有尺寸",
      seg.text_seg.width > 1 and seg.text_seg.height > 1,
      "%.1fx%.1f" % (seg.text_seg.width, seg.text_seg.height))
check("排序分段控件有尺寸",
      seg.sort_seg.width > 1 and seg.sort_seg.height > 1,
      "%.1fx%.1f" % (seg.sort_seg.width, seg.sort_seg.height))

# ============ 5. 模式联动（灰化） ============
print("=== 5. 分段页模式联动 ===")
seg.text_seg.select(0, notify=True)
check("文字区=保留原文 时字母输入框禁用", seg.text_start_input.disabled is True)
seg.text_seg.select(1, notify=True)
check("文字区=字母序号 时字母输入框启用", seg.text_start_input.disabled is False)
seg.text_seg.select(2, notify=True)
check("文字区=固定文字 时固定文字框启用", seg.text_fixed_input.disabled is False)
check("文字区=固定文字 时字母输入框禁用", seg.text_start_input.disabled is True)

seg.digit_seg.select(2, notify=True)
check("数字区=固定数字 时固定数字框启用", seg.digit_fixed_input.disabled is False)
check("数字区=固定数字 时起始数字框禁用", seg.start_input.disabled is True)
seg.digit_seg.select(0, notify=True)
check("数字区=保留原文 时固定数字框禁用", seg.digit_fixed_input.disabled is True)
seg.digit_seg.select(1, notify=True)
check("数字区=序号 时起始数字框启用", seg.start_input.disabled is False)

# ============ 6. 参数校验文案 ============
print("=== 6. 参数校验 ===")


def err_of(fn):
    try:
        fn()
        return "NO_ERROR"
    except ValueError as e:
        return str(e)
    except Exception as e:
        return "OTHER:" + repr(e)


seg.text_seg.select(2, notify=True)
seg.text_fixed_input.text = ""
msg = err_of(seg.collect_operations)
check("固定文字为空时给出中文提示", "固定文字" in msg, msg)

seg.text_seg.select(0, notify=True)
seg.digit_seg.select(2, notify=True)
seg.digit_fixed_input.text = ""
msg = err_of(seg.collect_operations)
check("固定数字为空时给出中文提示", "固定数字" in msg, msg)

seg.digit_seg.select(1, notify=True)
seg.step_input.text = "0"
msg = err_of(seg.collect_operations)
check("数字步长为 0 时给出中文提示", "步长" in msg, msg)
seg.step_input.text = "1"

seg.digits_input.text = "-1"
msg = err_of(seg.collect_operations)
check("补零位数为负时给出中文提示", "负" in msg, msg)
seg.digits_input.text = "2"

seg.start_input.text = "abc"
msg = err_of(seg.collect_operations)
check("非整数输入给出中文提示", "整数" in msg, msg)
seg.start_input.text = "1"

# ============ 7. 端到端：临时目录 预览→执行→撤回 ============
print("=== 7. 端到端预览→执行→撤回 ===")
tmp = tempfile.mkdtemp(prefix="seg_smoke_")
origin = ["旅行照片1.png", "旅行照片2.png", "旅行照片12.png"]
for n in origin:
    with open(os.path.join(tmp, n), "w", encoding="utf-8") as f:
        f.write("x")

seg.selected_folder = tmp
safe("设置文件夹后刷新标签", seg._refresh_folder_label)

seg.text_seg.select(1, notify=True)
seg.text_start_input.text = "1"
seg.text_step_input.text = "1"
seg.digit_seg.select(1, notify=True)
seg.start_input.text = "1"
seg.step_input.text = "1"
seg.digits_input.text = "2"
seg.adaptive_switch.active = True
seg.sep_input.text = "_"
seg.sort_seg.select(0, notify=True)

safe("点击预览", seg.preview, None)
print("    预览结果:\n%s" % (seg.result_label.text or ""))
check("预览生成了重命名计划", seg.plan is not None)
check("预览没有冲突", seg.plan is not None and not seg.plan.has_conflicts())

safe("点击执行", seg.execute, None)
after = sorted(n for n in os.listdir(tmp) if not n.startswith("."))
print("    执行后目录:", after)
check("文件已按「字母_序号」改名",
      {"a_01.png", "b_02.png", "c_03.png"}.issubset(set(after)), after)

safe("点击撤回", seg.undo, None)
back = sorted(n for n in os.listdir(tmp) if not n.startswith("."))
print("    撤回后目录:", back)
check("撤回后文件名还原", sorted(origin) == back, back)
shutil.rmtree(tmp, ignore_errors=True)

# ============ 8. 未选文件夹时的兜底提示 ============
print("=== 8. 未选文件夹兜底 ===")
for title, cls in ENTRIES:
    page = app._screens[cls]
    page.selected_folder = None
    safe("%s 未选文件夹点预览不崩" % cls.__name__, page.preview, None)
    safe("%s 未选文件夹点执行不崩" % cls.__name__, page.execute, None)

# ============ 9. 全局刷新 ============
print("=== 9. 全局刷新 ===")
seg.text_seg.select(1, notify=True)
safe("refresh_folder_labels 不崩", app.refresh_folder_labels)
check("刷新后各页 plan 被清空",
      all(getattr(app._screens[c], "plan", None) is None for _, c in ENTRIES))

# ============ 10. 分段页布局定稿契约 ============
print("=== 10. 分段页布局定稿 ===")
safe("回到分段页", app.go_screen, M.SegmentRenameScreen)
layout_now()
tips = texts_of(seg)
for t in ("① 文字区（前半段）", "② 数字区（后半段）",
          "③ 排序依据（决定谁排在前）"):
    check("分段页有分区标题 %s" % t, any(t in x for x in tips))
check("分段页有实时示例行", hasattr(seg, "sample_label"))
check("分段页有分隔符行引用", hasattr(seg, "label_sep"))
# --- 渐进式显隐：文字区 ---
seg.text_seg.select(0, notify=True)
layout_now()
check("文字区=保留原文 收起「字母起始」行",
      seg.label_text_start.height <= 0.5,
      "height=%.1f" % seg.label_text_start.height)
check("文字区=保留原文 收起「固定文字」行",
      seg.label_text_fixed.height <= 0.5)
seg.text_seg.select(1, notify=True)
layout_now()
check("文字区=字母序号 展开「字母起始」行",
      seg.label_text_start.height > 1,
      "height=%.1f" % seg.label_text_start.height)
check("文字区=字母序号 收起「固定文字」行",
      seg.label_text_fixed.height <= 0.5)
seg.text_seg.select(2, notify=True)
layout_now()
check("文字区=固定文字 展开「固定文字」行",
      seg.label_text_fixed.height > 1)
check("文字区=固定文字 收起「字母步长」行",
      seg.label_text_step.height <= 0.5)
# --- 渐进式显隐：数字区 ---
seg.digit_seg.select(0, notify=True)
layout_now()
check("数字区=保留原文 收起「补零位数」行",
      seg.label_digits.height <= 0.5)
check("数字区=保留原文 收起「起始于」行",
      seg.label_start.height <= 0.5)
seg.digit_seg.select(1, notify=True)
layout_now()
check("数字区=序号 展开「补零位数」行",
      seg.label_digits.height > 1)
check("数字区=序号 展开补零开关行",
      seg.arow.height > 1, "height=%.1f" % seg.arow.height)
check("数字区=序号 收起「固定数字」行",
      seg.label_digit_fixed.height <= 0.5)
try:
    _albl_w = seg.arow.children[-1].width
except Exception:
    _albl_w = 0
check("补零开关行文字标签宽度充足（不会被裁字）",
      _albl_w >= dp(190), "width=%.1f" % _albl_w)
seg.digit_seg.select(2, notify=True)
layout_now()
check("数字区=固定数字 展开「固定数字」行",
      seg.label_digit_fixed.height > 1)
# --- 实时示例随设置变化 ---
seg.text_seg.select(2, notify=True)
seg.text_fixed_input.text = "IMG"
seg.digit_seg.select(1, notify=True)
seg.start_input.text = "1"
seg.step_input.text = "1"
seg.digits_input.text = "3"
seg.adaptive_switch.active = True
seg.sep_input.text = "_"
safe("刷新示例", seg._update_sample)
print("    示例文本:", seg.sample_label.text)
check("示例反映「固定文字 + 分隔符 + 补零」",
      seg.sample_label.text == "示例：IMG_001 … 002.png",
      seg.sample_label.text)
seg.text_seg.select(0, notify=True)
seg.digit_seg.select(0, notify=True)
seg.sep_input.text = ""
safe("再刷新示例", seg._update_sample)
print("    示例文本:", seg.sample_label.text)
check("示例反映「保留原文 + 保留原文」",
      "旅行照片" in seg.sample_label.text and "12" in seg.sample_label.text,
      seg.sample_label.text)
seg.text_seg.select(1, notify=True)
seg.text_start_input.text = "3"
safe("再刷新示例（字母）", seg._update_sample)
print("    示例文本:", seg.sample_label.text)
check("示例反映「字母序号」第 3 个 = C",
      seg.sample_label.text.startswith("示例：C"),
      seg.sample_label.text)
# ============ 汇总 ============
print("\n================ 冒烟结果 ================")
print("通过: %d 项" % len(PASSED))
print("失败: %d 项" % len(FAILED))
for name in FAILED:
    print("  - 失败项: %s" % name)
sys.exit(1 if FAILED else 0)