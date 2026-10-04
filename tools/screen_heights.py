# -*- coding: utf-8 -*-
"""四页「内容高度 vs 视口高度」轻量体检脚本（只布局，不渲染、不截图）。

用途
----
Kivy 的 ScrollView 在真机（density=2.8125）下到底要滚多远，光看代码估不准。
本脚本按「真机密度」建窗，用分帧（Clock）逐页 ``go_screen``，等一帧布局后量出
每个功能页的 ScrollView 视口高与 page 内容高，打印成对照表。

为什么不用 to_window？
---------------------
ScrollView 内控件的 ``to_window()`` 返回值不可靠（曾被量成全部 -1616.2），所以这里只比
「视口高 vs ``page.minimum_height``」，不依赖控件绝对坐标。

怎么判读
--------
* 「需滚动=否」：一屏装得下，体验最好；
* 「超出量」就是真机上还要往下滑的像素数，除以 2400 就是还要滚几屏；
* 分段重命名页参数最多，历史上超出 1380px（≈1.6 屏），是重点盯防对象。

运行方式
--------
    cd <项目根目录>
    KIVY_METRICS_DENSITY=2.8125 xvfb-run -a -s "-screen 0 1080x2400x24" \\
        python3 tools/screen_heights.py

坑
--
* 必须先 ``pkill -9 -f Xvfb`` 清残留（llvmpipe 软件渲染吃内存，残留进程叠加会被 OOM 杀）；
* 不要用 ``app._screens.keys()`` 取页面列表——ScreenManager 懒加载，那里是空的，
  必须用下面显式的 ``SCREENS`` 列表；
* 任何布局改动后重跑本脚本做前后对比：只有目标页高度应变化，其余页数据应一字不变。
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.setdefault("KIVY_NO_ARGS", "1")

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)

from kivy.clock import Clock          # noqa: E402
from kivy.core.window import Window   # noqa: E402
from kivy.metrics import Metrics      # noqa: E402
from kivy.uix.scrollview import ScrollView  # noqa: E402

import main as M                      # noqa: E402

app = M.BatchRenamerApp()
root = app.build()
app.root = root

# 页面顺序：前三个是既有页，最后一个是分段重命名页（重点对比对象）
SCREENS = [M.PrefixSuffixScreen, M.ReplaceScreen,
           M.IndexScreen, M.SegmentRenameScreen]

RESULTS = []


def walk(w):
    yield w
    for c in list(w.children):
        yield from walk(c)


def find_one(rw, cls):
    for w in walk(rw):
        if isinstance(w, cls):
            return w
    return None


def report():
    print("density=%s  Window=%s  顶栏高(估)=%.1f"
          % (Metrics.density, tuple(Window.size), 64 * Metrics.density))
    print("%-22s %9s %9s %8s %9s" % ("页面", "视口高", "内容高", "需滚动", "超出量"))
    print("-" * 64)
    for name, vh, ch in RESULTS:
        print("%-22s %9.1f %9.1f %8s %9.1f"
              % (name, vh, ch, "是" if ch > vh + 1 else "否", max(0.0, ch - vh)))
    print("-" * 64)
    for name, vh, ch in RESULTS:
        print("  %s: 内容高 %.1f px ≈ %.1f 屏" % (name, ch, ch / vh if vh else 0))


def measure(cls):
    name = cls.__name__
    seg = app._screens.get(cls)
    sv = find_one(seg, ScrollView)
    if sv is None:
        print("!! %s 没有 ScrollView" % name)
        return
    page = sv.children[0] if sv.children else None
    print("  %-22s scroll=(%.0fx%.0f) page=(%.0fx%.0f) min_height=%.1f"
          % (name, sv.width, sv.height, page.width, page.height,
             page.minimum_height))
    RESULTS.append((name, sv.height, page.height))


def step(i=0):
    if i >= len(SCREENS):
        report()
        Clock.schedule_once(lambda d: app.stop(), 0.2)
        return
    cls = SCREENS[i]
    app.go_screen(cls)

    def done(dt):
        measure(cls)
        Clock.schedule_once(lambda d: step(i + 1), 0.15)

    Clock.schedule_once(done, 0.45)


def start(dt):
    step(0)


try:
    Window.size = (1080, 2400)
except Exception as e:
    print("set size fail:", e)

Clock.schedule_once(start, 0.5)
app.run()
