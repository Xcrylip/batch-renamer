"""
批量重命名工具 — Kivy 图形界面（分页式，每页只做一件事）

结构说明：
    首页只有 3 个入口按钮，每个入口进入一个「只负责单一功能」的页面：

        首页
         ├── 加前/后缀  -> 只做「前缀 + 后缀」两件事
         ├── 查找替换    -> 只做「查找替换」一件事
         └── 插入序号    -> 只做「插入序号」一件事

    三个功能页彼此完全独立（互斥）：
      * 每页只读取本页自己的输入控件来生成操作；
      * 每页各自维护独立的 self.plan，不会出现「A 页预览、B 页执行」的串台；
      * 公共操作区（选择文件夹 / 预览 / 执行 / 撤回）在每页都有一份，
        文件夹选择结果由 App 全局共享，切换页面后各页显示同步刷新。

    所有重命名逻辑仍然委托给 batch_renamer.core / operations，
    本文件只负责「界面 + 交互」。
"""

import os
import sys

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.switch import Switch
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, RoundedRectangle

# 让脚本能 import 到同目录下的 batch_renamer 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from batch_renamer.core import generate_plan, undo_rename
from batch_renamer.operations import (
    AddPrefix,
    AddSuffix,
    ReplaceText,
    InsertIndex,
)

LOG_NAME = ".batch_rename_log.json"


# ================= 中文字体注册 =================
# Kivy 默认字体 Roboto 不含中文，必须注册一个中文字体并覆盖默认名，
# 否则所有中文都会显示成方块（豆腐块）。
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_CANDIDATES = [
    "WenQuanYiMicroHei.ttf",
    "WenQuanYiMicroHei.ttc",
]
_FONT_LOADED = None  # None=未尝试, True=成功, False=失败


def register_chinese_font():
    """查找并注册中文字体，覆盖 Kivy 默认字体名 Roboto。

    返回 True 表示成功，False 表示未找到（此时程序仍可运行，但中文可能是方块）。
    """
    global _FONT_LOADED
    if _FONT_LOADED is not None:
        return _FONT_LOADED

    for name in FONT_CANDIDATES:
        path = os.path.join(FONT_DIR, name)
        if os.path.exists(path):
            try:
                LabelBase.register(name="Roboto", fn_regular=path)
                print(f"[字体] 已注册中文字体: {path}")
                _FONT_LOADED = True
                return True
            except Exception as e:  # pragma: no cover
                print(f"[字体] 注册失败 {path}: {e}")

    print("[字体] 警告：未找到中文字体，中文可能显示为方块")
    print(f"[字体] 期望位置: {FONT_DIR}")
    _FONT_LOADED = False
    return False


# ================= 配色（现代浅色主题） =================
COLOR_BG = (0.96, 0.965, 0.975, 1)        # 页面背景
COLOR_CARD = (1, 1, 1, 1)                 # 卡片背景
COLOR_TOPBAR = (0.129, 0.196, 0.325, 1)   # 顶部栏深蓝
COLOR_PRIMARY = (0.196, 0.463, 0.855, 1)  # 主蓝
COLOR_PRIMARY_D = (0.149, 0.365, 0.706, 1)  # 主蓝按下
COLOR_SUCCESS = (0.18, 0.639, 0.408, 1)   # 绿
COLOR_SUCCESS_D = (0.133, 0.494, 0.318, 1)
COLOR_WARN = (0.902, 0.522, 0.184, 1)     # 橙
COLOR_WARN_D = (0.71, 0.404, 0.137, 1)
COLOR_DANGER = (0.847, 0.278, 0.278, 1)   # 红
COLOR_TEXT = (0.129, 0.145, 0.176, 1)     # 主文字
COLOR_TEXT_SUB = (0.42, 0.45, 0.51, 1)    # 次要文字
COLOR_BORDER = (0.87, 0.89, 0.92, 1)      # 边框
COLOR_TERMINAL = (0.098, 0.114, 0.145, 1)  # 结果区深色底
COLOR_TERMINAL_TX = (0.36, 0.82, 0.502, 1)  # 结果区绿字

RADIUS = dp(10)


# ================= 绘图小工具 =================
def _draw_round(widget, rgba, radius=RADIUS):
    """给控件画一个圆角矩形背景。"""
    with widget.canvas.before:
        Color(*rgba)
        widget._rr = RoundedRectangle(
            pos=widget.pos, size=widget.size, radius=[radius]
        )

    def _upd(w, *a):
        w._rr.pos = w.pos
        w._rr.size = w.size

    widget.bind(pos=_upd, size=_upd)


def _draw_flat(widget, rgba):
    """给控件画一个直角矩形背景。"""
    with widget.canvas.before:
        Color(*rgba)
        widget._rect = Rectangle(pos=widget.pos, size=widget.size)

    def _upd(w, *a):
        w._rect.pos = w.pos
        w._rect.size = w.size

    widget.bind(pos=_upd, size=_upd)


def _bind_label(widget, **kwargs):
    """绑定控件的属性变化到 label 上（简易 KV 替代）。"""
    for key, value in kwargs.items():
        widget.bind(**{key: value})


# ================= 自定义控件 =================
class Card(BoxLayout):
    """白色圆角卡片容器。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", [dp(14), dp(12), dp(14), dp(12)])
        kwargs.setdefault("spacing", dp(10))
        kwargs.setdefault("size_hint_y", None)
        super().__init__(**kwargs)
        _draw_round(self, COLOR_CARD)
        self.bind(minimum_height=self.setter("height"))


class RoundButton(Button):
    """圆角按钮。"""

    def __init__(self, bg=COLOR_PRIMARY, bg_down=COLOR_PRIMARY_D, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("color", (1, 1, 1, 1))
        kwargs.setdefault("font_size", "15sp")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(44))
        super().__init__(**kwargs)
        self.radius = [RADIUS]

        with self.canvas.before:
            self._c = Color(*bg)
            self._rr = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[RADIUS]
            )
        self._bg = bg
        self._bg_down = bg_down

        def _upd(w, *a):
            w._rr.pos = w.pos
            w._rr.size = w.size

        self.bind(pos=_upd, size=_upd)
        self.bind(state=self._on_state)

    def _on_state(self, widget, state):
        self._c.rgba = self._bg_down if state == "down" else self._bg


class FieldInput(TextInput):
    """统一样式的输入框。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("font_size", "15sp")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(42))
        kwargs.setdefault("padding", [dp(10), dp(10), dp(10), dp(10)])
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_active", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("foreground_color", COLOR_TEXT)
        kwargs.setdefault("cursor_color", COLOR_PRIMARY)
        kwargs.setdefault("hint_text_color", (0.6, 0.63, 0.68, 1))
        super().__init__(**kwargs)
        _draw_round(self, (0.965, 0.97, 0.98, 1), radius=dp(8))


class LabeledField(BoxLayout):
    """一行：左边标签 + 右边输入框。"""

    def __init__(self, label_text, input_widget, label_width=dp(78), **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(42))
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)

        lbl = Label(
            text=label_text,
            color=COLOR_TEXT,
            font_size="14sp",
            size_hint_x=None,
            width=label_width,
            halign="left",
            valign="middle",
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(lbl)

        input_widget.size_hint_x = 1
        input_widget.size_hint_y = 1
        input_widget.height = dp(42)
        self.add_widget(input_widget)
        self.input = input_widget


# ================= 功能页基类 =================
class FeatureScreen(Screen):
    """所有「单一功能页」的基类。

    子类只需实现：
        PAGE_TITLE        —— 页面标题（显示在顶部栏）
        PAGE_SUBTITLE     —— 页面副标题
        build_ops_card()  —— 返回本页专属的参数输入卡片
        collect_operations() —— 把本页输入翻译成操作对象列表
    """

    PAGE_TITLE = "功能"
    PAGE_SUBTITLE = "本页只应用这里的设置"

    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.plan = None  # 本页独立的执行计划
        self.selected_folder = app_ref.selected_folder

        root = BoxLayout(orientation="vertical")
        _draw_flat(root, COLOR_BG)
        self.add_widget(root)

        # 顶部栏
        root.add_widget(self._build_topbar())

        # 可滚动主体
        scroll = ScrollView(size_hint=(1, 1))
        page = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=[dp(12), dp(14), dp(12), dp(20)],
            spacing=dp(14),
        )
        page.bind(minimum_height=page.setter("height"))

        # 专属参数卡片
        page.add_widget(self.build_ops_card())

        # 公共操作区
        page.add_widget(self._build_action_card())

        # 执行结果区
        page.add_widget(self._build_result_card())

        scroll.add_widget(page)
        root.add_widget(scroll)

        # 文件夹显示标签（各页同步）
        self._refresh_folder_label()

    # ---------- 顶部栏 ----------
    def _build_topbar(self):
        bar = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(64),
            padding=[dp(10), dp(8), dp(12), dp(8)],
            spacing=dp(10),
        )
        _draw_flat(bar, COLOR_TOPBAR)

        back = RoundButton(text="返回", bg=COLOR_PRIMARY_D,
                           bg_down=COLOR_PRIMARY, size_hint_x=None, width=dp(64))
        back.bind(on_release=lambda *a: self.app_ref.go_home())
        bar.add_widget(back)

        titles = BoxLayout(orientation="vertical", spacing=dp(0))
        t1 = Label(
            text=self.PAGE_TITLE,
            color=(1, 1, 1, 1),
            font_size="18sp",
            bold=True,
            halign="left",
            valign="middle",
        )
        t1.bind(size=lambda w, s: setattr(w, "text_size", s))
        t2 = Label(
            text=self.PAGE_SUBTITLE,
            color=(0.75, 0.8, 0.88, 1),
            font_size="12sp",
            halign="left",
            valign="middle",
        )
        t2.bind(size=lambda w, s: setattr(w, "text_size", s))
        titles.add_widget(t1)
        titles.add_widget(t2)
        bar.add_widget(titles)
        return bar

    # ---------- 公共操作区 ----------
    def _build_action_card(self):
        card = Card()

        # 文件夹显示
        self.folder_label = Label(
            text="未选择文件夹",
            color=COLOR_TEXT_SUB,
            font_size="13sp",
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        self.folder_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        card.add_widget(self.folder_label)

        row1 = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(44), spacing=dp(10))
        self.btn_choose = RoundButton(text="选择文件夹", bg=COLOR_PRIMARY,
                                      bg_down=COLOR_PRIMARY_D)
        self.btn_choose.bind(on_release=self.open_file_chooser)
        row1.add_widget(self.btn_choose)

        self.btn_preview = RoundButton(text="预览", bg=COLOR_PRIMARY,
                                       bg_down=COLOR_PRIMARY_D)
        self.btn_preview.bind(on_release=self.preview)
        row1.add_widget(self.btn_preview)
        card.add_widget(row1)

        row2 = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(44), spacing=dp(10))
        self.btn_exec = RoundButton(text="执行", bg=COLOR_SUCCESS,
                                    bg_down=COLOR_SUCCESS_D)
        self.btn_exec.bind(on_release=self.execute)
        row2.add_widget(self.btn_exec)

        self.btn_undo = RoundButton(text="撤回", bg=COLOR_WARN,
                                    bg_down=COLOR_WARN_D)
        self.btn_undo.bind(on_release=self.undo)
        row2.add_widget(self.btn_undo)
        card.add_widget(row2)

        tip = Label(
            text="建议先「预览」确认无误，再「执行」。",
            color=COLOR_TEXT_SUB,
            font_size="12sp",
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
        )
        tip.bind(size=lambda w, s: setattr(w, "text_size", s))
        card.add_widget(tip)
        return card

    # ---------- 执行结果区 ----------
    def _build_result_card(self):
        card = Card()
        card.add_widget(self._section_title("执行结果"))

        self.result_label = Label(
            text="（尚未执行）",
            color=COLOR_TERMINAL_TX,
            font_size="13sp",
            size_hint_y=None,
            height=dp(120),
            halign="left",
            valign="top",
            markup=False,
        )
        self.result_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        _draw_round(self.result_label, COLOR_TERMINAL, radius=dp(8))
        self.result_label.padding = [dp(10), dp(10)]
        card.add_widget(self.result_label)
        return card

    # ---------- 小工具 ----------
    def _section_title(self, text):
        lbl = Label(
            text=text,
            color=COLOR_TEXT,
            font_size="15sp",
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        return lbl

    def _divider(self):
        w = Widget(size_hint_y=None, height=dp(1))
        _draw_flat(w, COLOR_BORDER)
        return w

    # ---------- 子类必须实现 ----------
    def build_ops_card(self):
        raise NotImplementedError

    def collect_operations(self):
        """返回本页的操作对象列表（互斥的根源：只读本页控件）。"""
        raise NotImplementedError

    # ---------- 文件夹 ----------
    def open_file_chooser(self, instance):
        """打开系统文件选择器（Android）或弹出路径输入（桌面）。"""
        if hasattr(self.app_ref, "open_file_chooser"):
            self.app_ref.open_file_chooser(
                on_selected=self._on_folder_selected
            )
        else:
            self.show_message("当前平台不支持文件夹选择")

    def _on_folder_selected(self, folder):
        self.selected_folder = folder
        self.app_ref.selected_folder = folder
        self.app_ref.refresh_folder_labels()
        self.plan = None

    def _refresh_folder_label(self):
        if self.selected_folder:
            try:
                n = len(os.listdir(self.selected_folder))
            except Exception:
                n = 0
            self.folder_label.text = f"文件夹：{self.selected_folder}（约 {n} 项）"
        else:
            self.folder_label.text = "未选择文件夹"

    def get_files_in_folder(self):
        """读取文件夹中的文件名列表（跳过隐藏文件和日志文件）。

        注意：core.generate_plan 接收的是「文件名」列表（配合 base_dir 参数
        拼成绝对路径），所以这里返回字符串列表，而不是某个 FileItem 对象。
        """
        if not self.selected_folder:
            return []
        names_out = []
        try:
            names = sorted(os.listdir(self.selected_folder))
        except Exception as e:
            self.show_message(f"读取文件夹失败: {e}")
            return []
        for name in names:
            if name.startswith("."):
                continue
            if name == LOG_NAME:
                continue
            full = os.path.join(self.selected_folder, name)
            if os.path.isfile(full):
                names_out.append(name)
        return names_out

    def log_path(self):
        if not self.selected_folder:
            return LOG_NAME
        return os.path.join(self.selected_folder, LOG_NAME)

    # ---------- 预览 ----------
    def preview(self, instance):
        if not self.selected_folder:
            self.show_message("请先选择文件夹")
            return
        try:
            ops = self.collect_operations()
        except ValueError as e:
            self.show_message(str(e))
            return

        if not ops:
            self.show_message("本页还没有可用的设置，请先填写参数")
            return

        files = self.get_files_in_folder()
        if not files:
            self.show_message("文件夹里没有可处理的文件")
            return

        try:
            self.plan = generate_plan(files, ops, base_dir=self.selected_folder)
        except Exception as e:
            self.show_message(f"生成计划失败: {e}")
            return

        lines = ["预览（尚未改动任何文件）", ""]
        count = 0
        for old_path, new_path in self.plan.pairs.items():
            old_name = os.path.basename(old_path)
            new_name = os.path.basename(new_path)
            if old_name != new_name:
                count += 1
                lines.append(f"{old_name}")
                lines.append(f"    -> {new_name}")
        if count == 0:
            lines.append("（没有文件会被改动）")
        else:
            lines.insert(1, f"共 {count} 个文件将被重命名")
        # 冲突提醒：目标名重复或会覆盖已有文件
        if self.plan.has_conflicts():
            lines.append("")
            lines.append("注意：存在重命名冲突，请先调整参数！")
            for bad in self.plan.conflicts():
                lines.append(f"    冲突：{os.path.basename(bad)}")
        self.result_label.text = "\n".join(lines)

    # ---------- 执行 ----------
    def execute(self, instance):
        if not self.selected_folder:
            self.show_message("请先选择文件夹")
            return
        if self.plan is None:
            self.show_message("请先「预览」确认后再执行")
            return
        if self.plan.has_conflicts():
            self.show_message("存在重命名冲突，请先调整参数再执行")
            return
        try:
            self.plan.execute(log_path=self.log_path())
            self.result_label.text = "重命名完成"
            self.plan = None
        except Exception as e:
            self.show_message(f"执行失败: {e}")

    # ---------- 撤回 ----------
    def undo(self, instance):
        if not self.selected_folder:
            self.show_message("请先选择文件夹")
            return
        try:
            undo_rename(log_path=self.log_path())
            self.result_label.text = "已撤销"
            self.plan = None
        except FileNotFoundError:
            self.show_message("这个文件夹没有可撤销的记录")
        except Exception as e:
            self.show_message(f"撤销失败: {e}")

    def show_message(self, message):
        popup = Popup(
            title="提示",
            content=Label(text=message, font_size="15sp"),
            size_hint=(0.8, 0.4),
        )
        popup.open()


# ================= 页面 1：加前/后缀 =================
class PrefixSuffixScreen(FeatureScreen):
    PAGE_TITLE = "加前/后缀"
    PAGE_SUBTITLE = "只处理前缀和后缀，不影响其他设置"

    def build_ops_card(self):
        card = Card()
        card.add_widget(self._section_title("前缀 / 后缀"))

        self.prefix_input = FieldInput(hint_text="例如：2024_（留空则不加）")
        card.add_widget(LabeledField("前缀", self.prefix_input))

        self.suffix_input = FieldInput(hint_text="例如：_终稿（留空则不加）")
        card.add_widget(LabeledField("后缀", self.suffix_input))

        note = Label(
            text="说明：前缀加在文件名最前面，后缀加在扩展名之前。",
            color=COLOR_TEXT_SUB,
            font_size="12sp",
            size_hint_y=None,
            height=dp(34),
            halign="left",
            valign="middle",
        )
        note.bind(size=lambda w, s: setattr(w, "text_size", s))
        card.add_widget(note)
        return card

    def collect_operations(self):
        ops = []
        prefix = self.prefix_input.text
        suffix = self.suffix_input.text
        if prefix:
            ops.append(AddPrefix(prefix=prefix))
        if suffix:
            ops.append(AddSuffix(suffix=suffix))
        return ops


# ================= 页面 2：查找替换 =================
class ReplaceScreen(FeatureScreen):
    PAGE_TITLE = "查找替换"
    PAGE_SUBTITLE = "只做查找替换，不影响其他设置"

    def build_ops_card(self):
        card = Card()
        card.add_widget(self._section_title("查找替换"))

        self.find_input = FieldInput(hint_text="要被替换掉的内容")
        card.add_widget(LabeledField("查找", self.find_input))

        self.replace_input = FieldInput(hint_text="替换成什么（留空则删除）")
        card.add_widget(LabeledField("替换为", self.replace_input))

        note = Label(
            text="说明：只替换文件名中匹配到的文字，可以留空表示删除。",
            color=COLOR_TEXT_SUB,
            font_size="12sp",
            size_hint_y=None,
            height=dp(34),
            halign="left",
            valign="middle",
        )
        note.bind(size=lambda w, s: setattr(w, "text_size", s))
        card.add_widget(note)
        return card

    def collect_operations(self):
        find = self.find_input.text
        if not find:
            return []
        return [ReplaceText(old=find, new=self.replace_input.text)]


# ================= 页面 3：插入序号 =================
class IndexScreen(FeatureScreen):
    PAGE_TITLE = "插入序号"
    PAGE_SUBTITLE = "只插入序号，不影响其他设置"

    def build_ops_card(self):
        card = Card()
        card.add_widget(self._section_title("插入序号"))

        # 开关行
        row = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(40), spacing=dp(8))
        lbl = Label(
            text="启用序号",
            color=COLOR_TEXT,
            font_size="14sp",
            size_hint_x=None,
            width=dp(78),
            halign="left",
            valign="middle",
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        row.add_widget(lbl)

        self.index_switch = Switch(active=False, size_hint_x=None, width=dp(60))
        self.index_switch.bind(active=self._on_index_toggle)
        row.add_widget(self.index_switch)

        spacer = Widget()
        row.add_widget(spacer)
        card.add_widget(row)

        # 起始 / 位数
        self.start_input = FieldInput(text="1", hint_text="起始数字")
        self.start_input.input_filter = "int"
        self.label_start = LabeledField("起始于", self.start_input)
        card.add_widget(self.label_start)

        self.digits_input = FieldInput(text="3", hint_text="序号位数")
        self.digits_input.input_filter = "int"
        self.label_digits = LabeledField("位数", self.digits_input)
        card.add_widget(self.label_digits)

        # 位置（0 = 文件名开头，1 = 扩展名前/末尾）
        self.position_input = FieldInput(text="1", hint_text="0=开头, 1=末尾")
        self.position_input.input_filter = "int"
        self.label_position = LabeledField("插入位置", self.position_input)
        card.add_widget(self.label_position)

        note = Label(
            text="说明：位置 0 表示加在文件名开头，1 表示加在扩展名之前（末尾）。",
            color=COLOR_TEXT_SUB,
            font_size="12sp",
            size_hint_y=None,
            height=dp(34),
            halign="left",
            valign="middle",
        )
        note.bind(size=lambda w, s: setattr(w, "text_size", s))
        card.add_widget(note)

        self._set_index_params_enabled(False)
        return card

    def _on_index_toggle(self, instance, active):
        self._set_index_params_enabled(active)

    def _set_index_params_enabled(self, enabled):
        for w in (self.start_input, self.digits_input, self.position_input):
            w.disabled = not enabled

    def collect_operations(self):
        if not self.index_switch.active:
            return []
        try:
            start = int(self.start_input.text or "1")
            digits = int(self.digits_input.text or "3")
            pos_flag = int(self.position_input.text or "1")
        except ValueError:
            raise ValueError("序号设置里必须填整数")
        if digits < 1:
            raise ValueError("位数至少为 1")
        # core.operations.InsertIndex 的 position 只接受 'start' / 'end'
        position = "start" if pos_flag == 0 else "end"
        return [InsertIndex(start=start, digits=digits, position=position)]


# ================= 首页 =================
class HomeScreen(Screen):
    """首页：只有 3 个功能入口按钮。"""

    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref

        root = BoxLayout(orientation="vertical")
        _draw_flat(root, COLOR_BG)
        self.add_widget(root)

        # 顶部标题栏
        bar = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(84),
            padding=[dp(16), dp(12), dp(16), dp(12)],
            spacing=dp(2),
        )
        _draw_flat(bar, COLOR_TOPBAR)

        t1 = Label(
            text="批量重命名",
            color=(1, 1, 1, 1),
            font_size="22sp",
            bold=True,
            halign="left",
            valign="middle",
        )
        t1.bind(size=lambda w, s: setattr(w, "text_size", s))
        t2 = Label(
            text="选择一个功能开始",
            color=(0.75, 0.8, 0.88, 1),
            font_size="13sp",
            halign="left",
            valign="middle",
        )
        t2.bind(size=lambda w, s: setattr(w, "text_size", s))
        bar.add_widget(t1)
        bar.add_widget(t2)
        root.add_widget(bar)

        # 当前文件夹提示（全局共享）
        self.folder_label = Label(
            text="未选择文件夹",
            color=COLOR_TEXT_SUB,
            font_size="13sp",
            size_hint_y=None,
            height=dp(30),
            padding=[dp(16), dp(0)],
            halign="left",
            valign="middle",
        )
        self.folder_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.folder_label)

        # 功能入口
        page = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=[dp(16), dp(10), dp(16), dp(20)],
            spacing=dp(14),
        )
        page.bind(minimum_height=page.setter("height"))
        page.add_widget(self._entry_button(
            "加前/后缀", "给文件名加前缀、加后缀", PrefixSuffixScreen, COLOR_PRIMARY))
        page.add_widget(self._entry_button(
            "查找替换", "把文件名里的某些文字换掉", ReplaceScreen, COLOR_SUCCESS))
        page.add_widget(self._entry_button(
            "插入序号", "给文件按顺序编号", IndexScreen, COLOR_WARN))
        root.add_widget(page)
        root.add_widget(Widget())  # 底部弹簧，吃掉剩余空间

        self._refresh_folder_label()

    def _entry_button(self, title, subtitle, screen_cls, color):
        """构造一个入口卡片（标题 + 说明 + 箭头）。

        实现要点（避免「按钮空白 + 点击闪退」）：
          * 用 RoundButton，它自带圆角背景与按压态；
          * 内部文字用一个 RelativeLayout 作为子控件「真正挂载」到按钮上，
            而不是只 bind pos/size —— 之前 inner 从未 add_widget(btn)，
            导致它不在渲染树里：既看不见文字，点击时也拿不到内容。
        """
        btn = RoundButton(
            text="",
            bg=color,
            bg_down=color,
            size_hint_y=None,
            height=dp(76),
        )

        # 用 RelativeLayout 让内部内容随按钮自动布局
        inner = RelativeLayout()
        t1 = Label(
            text=title,
            color=(1, 1, 1, 1),
            font_size="18sp",
            bold=True,
            halign="left",
            valign="middle",
            size_hint=(None, None),
        )
        t1.bind(size=lambda w, s: setattr(w, "text_size", s))
        t2 = Label(
            text=subtitle + "  >",
            color=(0.93, 0.95, 1, 1),
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint=(None, None),
        )
        t2.bind(size=lambda w, s: setattr(w, "text_size", s))

        def _layout_inner(w, *a):
            """把标题/说明按按钮实际尺寸摆放。"""
            pad = dp(18)
            inner.pos = w.pos
            inner.size = w.size
            w1 = max(dp(1), w.width - pad * 2)
            h1 = dp(30)
            h2 = dp(22)
            total = h1 + dp(2) + h2
            top = w.y + (w.height + total) / 2.0
            # 顶部标题
            t1.size = (w1, h1)
            t1.text_size = (w1, h1)
            t1.pos = (w.x + pad, top - h1)
            # 底部说明
            t2.size = (w1, h2)
            t2.text_size = (w1, h2)
            t2.pos = (w.x + pad, top - h1 - dp(2) - h2)

        inner.add_widget(t1)
        inner.add_widget(t2)
        btn.add_widget(inner)              # ★ 关键：真正挂载，才能显示文字
        btn.bind(pos=_layout_inner, size=_layout_inner)

        btn.bind(on_release=lambda *a: self.app_ref.go_screen(screen_cls))
        return btn

    def _refresh_folder_label(self):
        if self.app_ref.selected_folder:
            self.folder_label.text = f"当前文件夹：{self.app_ref.selected_folder}"
        else:
            self.folder_label.text = "尚未选择文件夹（进入功能页后选择）"


# ================= App 主类 =================
class BatchRenamerApp(App):
    """应用根对象。

    职责：
      * 启动时注册中文字体、申请 Android 权限；
      * 搭建 ScreenManager（首页 + 3 个功能页）；
      * 维护全局选中的文件夹，并提供 go_home / go_screen / refresh_folder_labels。
    """

    title = "批量重命名"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_folder = None
        self._screens = {}  # 类 -> 实例，避免重复创建

    # ---------- 生命周期 ----------
    def build(self):
        register_chinese_font()

        # 延迟一点点申请权限，避免和窗口初始化抢资源
        Clock.schedule_once(lambda dt: self._request_android_permissions(), 1.0)

        self.sm = ScreenManager(transition=SlideTransition())
        self.home = HomeScreen(app_ref=self)
        self.home.name = "home"
        self.sm.add_widget(self.home)
        return self.sm

    def on_start(self):
        self._check_manage_storage()

    # ---------- 导航 ----------
    def go_home(self):
        """回到首页。"""
        try:
            self.sm.transition.direction = "right"
        except Exception:
            pass
        self.sm.current = "home"

    def go_screen(self, screen_cls):
        """切到某个功能页（首次访问时创建）。"""
        scr = self._screens.get(screen_cls)
        if scr is None:
            scr = screen_cls(app_ref=self)
            scr.name = screen_cls.__name__
            self._screens[screen_cls] = scr
            self.sm.add_widget(scr)
        scr.selected_folder = self.selected_folder
        scr._refresh_folder_label()
        self.sm.transition.direction = "left"
        self.sm.current = scr.name

    def refresh_folder_labels(self):
        """文件夹变化后，同步刷新所有页面上的显示。"""
        self.home._refresh_folder_label()
        for scr in self._screens.values():
            scr.selected_folder = self.selected_folder
            scr._refresh_folder_label()
            scr.plan = None

    # ---------- 文件夹选择 ----------
    def open_file_chooser(self, on_selected=None):
        """Android 优先用系统文件选择器，桌面端回退到路径输入弹窗。"""
        if self._try_android_chooser(on_selected):
            return
        self._fallback_path_dialog(on_selected)

    def _try_android_chooser(self, on_selected):
        """尝试调用 Android 原生目录选择（通过 pyjnius）。"""
        try:
            from jnius import autoclass  # noqa
        except Exception:
            return False

        try:
            from android import activity  # noqa
            from android.permissions import request_permissions, Permission
        except Exception:
            return False

        try:
            # 这里使用的是 Kivy 常见的「目录选择」openDocumentTree 方案。
            # 若设备不支持，会抛异常，自动退回路径输入。
            from jnius import autoclass
            from android import mActivity

            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            Environment = autoclass("android.os.Environment")

            def _on_activity_result(request_code, result_code, intent):
                if intent is None:
                    return
                uri = intent.getData()
                if uri is None:
                    return
                path = self._uri_to_path(uri)
                if path and on_selected:
                    on_selected(path)

            activity.bind(on_activity_result=_on_activity_result)

            intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            mActivity.startActivityForResult(intent, 1001)
            return True
        except Exception as e:
            print(f"[选择文件夹] Android 选择器不可用: {e}")
            return False

    @staticmethod
    def _uri_to_path(uri):
        """把 content:// 的 tree uri 尽量还原成文件路径。"""
        try:
            from jnius import autoclass
            DocumentsContract = autoclass("android.provider.DocumentsContract")
            doc_id = DocumentsContract.getTreeDocumentId(uri)
            if ":" in doc_id:
                parts = doc_id.split(":")
                vol, rel = parts[0], parts[1]
                if vol.lower() == "primary":
                    base = "/storage/emulated/0"
                else:
                    base = f"/storage/{vol}"
                return os.path.join(base, rel) if rel else base
        except Exception as e:
            print(f"[选择文件夹] 解析路径失败: {e}")
        return None

    def _fallback_path_dialog(self, on_selected):
        """桌面端：弹一个输入框让用户手填路径。"""
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        ti = TextInput(text=self.selected_folder or "/storage/emulated/0",
                       multiline=False, size_hint_y=None, height=dp(42))
        box.add_widget(Label(text="请输入文件夹完整路径：", size_hint_y=None,
                             height=dp(30)))
        box.add_widget(ti)

        popup = Popup(title="选择文件夹", content=box, size_hint=(0.9, 0.4))

        def _ok(*a):
            path = ti.text.strip()
            if path and os.path.isdir(path):
                if on_selected:
                    on_selected(path)
                popup.dismiss()
            else:
                self.show_message("路径不存在或不是文件夹")

        btn = RoundButton(text="确定", size_hint_y=None, height=dp(44))
        btn.bind(on_release=_ok)
        box.add_widget(btn)
        popup.open()

    # ---------- 权限 ----------
    def _request_android_permissions(self):
        """申请存储相关权限（Android 6+ 需要运行时申请）。"""
        try:
            from android.permissions import request_permissions, Permission
        except Exception:
            return  # 非 Android 平台，跳过
        try:
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])
        except Exception as e:
            print(f"[权限] 申请失败: {e}")

    def _check_manage_storage(self):
        """Android 11+ 需要 MANAGE_EXTERNAL_STORAGE 才能访问任意目录。

        这里只做提示，不强行跳转设置（跳转会让首次启动体验变差）。
        """
        try:
            from jnius import autoclass
            Environment = autoclass("android.os.Environment")
            if not Environment.isExternalStorageManager():
                print("[权限] 提示：如需访问所有文件，请在系统设置里授予「所有文件访问」权限")
        except Exception:
            pass

    # ---------- 通用弹窗 ----------
    def show_message(self, message):
        popup = Popup(
            title="提示",
            content=Label(text=message, font_size="15sp"),
            size_hint=(0.8, 0.4),
        )
        popup.open()


if __name__ == "__main__":
    BatchRenamerApp().run()
