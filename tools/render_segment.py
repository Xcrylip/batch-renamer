# -*- coding: utf-8 -*-
"""分段重命名页「真机尺寸」渲染脚本（真事件循环 + 整页 FBO）。

用途
----
把 SegmentRenameScreen 在「真机密度」下渲染成两类图，供肉眼 / OCR 复核布局：

* ``viewport_<模式>0001.png`` —— 真机首屏（1080x2400），用 ``Window.screenshot()`` 取得；
* ``fullpage_<模式>.png``     —— 整页（不受 ScrollView 裁剪），用 ``Fbo`` 直接画 ``page`` 子树。

为什么不能只截首屏？
--------------------
分段页参数比其它功能页多，真机密度下内容高于一屏，底部「执行」按钮在可滚区末尾。
只截首屏会看不到按钮，所以额外做整页 FBO 渲染（画法与 Kivy 官方
``Widget.export_as_image`` 一致）。

运行方式（Ubuntu 容器 / 已装 Kivy + xvfb）
------------------------------------------
.. code-block:: bash

    cd <项目根目录>
    KIVY_METRICS_DENSITY=2.8125 \
    xvfb-run -a -s "-screen 0 1080x2400x24" python3 tools/render_segment.py

两个坑（本脚本已规避 / 已在注释里说明）
--------------------------------------
1. **密度**：真机 ``density = 2.8125``（红米 Note 14，``wm density`` = 450）。
   容器里 Kivy 默认按 ``density = 1`` 渲染，控件尺寸会小 2.8 倍，
   必须用官方开关 ``KIVY_METRICS_DENSITY`` 模拟，否则一切排版结论都是错的。
2. **内存**：软件渲染（llvmpipe）跑主循环 + 整页 FBO 很吃内存，
   上一次的 Xvfb / python 未退出时再次运行会被 OOM 杀掉（日志只剩 ``Killed``）。
   跑之前建议先清理残留：

   .. code-block:: bash

       pkill -9 -f Xvfb; pkill -9 -f render_segment

产物默认写到 ``tools/shots/``（该目录已在 ``.gitignore`` 中忽略）。
"""
import os
import sys
import glob
import shutil
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
from kivy.graphics import (Fbo, ClearColor, ClearBuffers,   # noqa: E402
                           Translate, Scale)
from kivy.metrics import Metrics      # noqa: E402
from PIL import Image                 # noqa: E402
import main as M                      # noqa: E402

SCREEN_W, SCREEN_H = 1080, 2400       # 真机分辨率
OUT = os.path.join(PROJ, "tools", "shots")

# 三种典型模式（正好覆盖三种分段按钮组合）
MODES = [
    ("A_序号模式", dict(text=1, digit=1, ts="1", tst="1", ds="1", dst="1",
                        digits="3", sep="_")),
    ("B_固定模式", dict(text=2, digit=2, tf="IMG", df="007", sep="_")),
    ("C_默认", dict(text=0, digit=0, sep="_")),
]


def walk(w):
    yield w
    for c in list(w.children):
        yield from walk(c)


def find_one(root_w, cls):
    for w in walk(root_w):
        if isinstance(w, cls):
            return w
    return None


def render_widget(widget, path, bg=(1, 1, 1, 1)):
    """照搬 Kivy 官方 Widget.export_as_image 的 Fbo 画法（含 canvas 摘取/回插）。"""
    w = max(int(round(widget.width)), 1)
    h = max(int(round(widget.height)), 1)
    parent = widget.parent
    idx = -1
    if parent is not None:
        try:
            idx = parent.canvas.indexof(widget.canvas)
        except Exception:
            idx = -1
        if idx > -1:
            parent.canvas.remove(widget.canvas)
    img = None
    fbo = Fbo(size=(w, h), with_stencilbuffer=True)
    try:
        with fbo:
            ClearColor(*bg)
            ClearBuffers()
            Scale(1, -1, 1)
            Translate(-widget.x, -widget.y - widget.height, 0)
        fbo.add(widget.canvas)
        fbo.draw()
        raw = fbo.pixels
        img = Image.frombytes("RGBA", (w, h), raw).convert("RGB")
        fbo.remove(widget.canvas)
    except Exception:
        traceback.print_exc()
        return None
    finally:
        if parent is not None and idx > -1:
            parent.canvas.insert(idx, widget.canvas)
    if img is None:
        return None
    img.save(path)
    print("    全页 -> %s  %dx%d" % (os.path.basename(path), w, h))
    return path


def apply_mode(m):
    seg = app._screens.get(M.SegmentRenameScreen)
    seg.text_seg.select(m.get("text", 0), notify=True)
    seg.digit_seg.select(m.get("digit", 0), notify=True)
    for key, attr in (("ts", "text_start_input"), ("tst", "text_step_input"),
                      ("tf", "text_fixed_input"), ("ds", "start_input"),
                      ("dst", "step_input"), ("digits", "digits_input"),
                      ("df", "digit_fixed_input"), ("sep", "sep_input")):
        if key in m:
            getattr(seg, attr).text = m[key]
    app.root.do_layout()
    print("    切模式: 示例行=%r" % seg.sample_label.text)


def shot_pair(tag):
    """先截首屏（必须 os.chdir，Window.screenshot 只认文件名），再整页 FBO。"""
    old = os.getcwd()
    os.chdir(OUT)
    try:
        p = Window.screenshot(name="viewport_" + tag + ".png")
    finally:
        os.chdir(old)
    print("    视口 ->", os.path.basename(p))
    seg = app._screens.get(M.SegmentRenameScreen)
    sv = find_one(seg, M.ScrollView)
    page = sv.children[0] if sv and sv.children else None
    if page is not None:
        render_widget(page, os.path.join(OUT, "fullpage_" + tag + ".png"))


def start(dt):
    print("density=%s  窗口尺寸=%s" % (Metrics.density, Window.size))
    app.go_screen(M.SegmentRenameScreen)
    delay = 0.0
    for tag, m in MODES:
        delay += 0.8

        def one(dt2, m=m, tag=tag):
            apply_mode(m)
            Clock.schedule_once(lambda dt3: shot_pair(tag), 0.4)

        Clock.schedule_once(one, delay)
    Clock.schedule_once(lambda dt4: app.stop(), delay + 1.0)


app = M.BatchRenamerApp()
app.root = app.build()

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)

try:
    Window.size = (SCREEN_W, SCREEN_H)
except Exception as e:
    print("set size fail:", e)
Clock.schedule_once(start, 0.8)
app.run()

print("=== 产物 ===")
for f in sorted(glob.glob(os.path.join(OUT, "*.png"))):
    im = Image.open(f).convert("RGB")
    cols = im.getcolors(maxcolors=2000000) or []
    print("   %-34s %-12s %8d字节 颜色数=%d"
          % (os.path.basename(f), str(im.size), os.path.getsize(f), len(cols)))
print("提示：整页高 > %d 说明真机上必须滚动。" % SCREEN_H)
