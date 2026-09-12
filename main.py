"""
批量重命名工具 — Kivy 图形界面（现代浅色主题）

设计说明：
    本文件只负责「界面 + 交互」，所有重命名逻辑都委托给 batch_renamer.core。
    功能与旧版完全一致（选择文件夹 / 前缀 / 后缀 / 替换 / 插入序号 / 预览 / 执行 / 撤销），
    只重做了视觉与布局：

      - 顶部：彩色标题栏（深蓝底 + 白字）
      - 文件夹卡片：展示当前路径 + 圆角主按钮
      - 规则卡片：前缀 / 后缀 / 替换 / 插入序号，每项一行「说明 + 圆角输入框」
      - 操作卡片：蓝（预览）/ 绿（执行）/ 橙（撤销）三个圆角按钮
      - 结果卡片：深色终端风，方便对齐看「原名 -> 新名」

实现要点：
    Kivy 原生控件没有圆角 / background_color，本文件用 canvas.before 手绘
    RoundedRectangle 来模拟。所有自绘背景的控件都必须在 pos/size 变化时同步
    canvas（在 Android 上尤其重要，避免旋转屏幕或软键盘弹出后错位）。

中文字体：
    Kivy 自带的 Roboto 字体**不含任何汉字**，如果不替换默认字体，界面上所有
    中文都会渲染成"豆腐块"方框（典型表现是每个字都变成一个带叉的方框）。
    这里的做法是：启动时把 fonts/ 下的文泉驿微米黑注册为 Kivy 的默认字体
    （'Roboto'），这样所有控件无需逐个指定 font_name 就能正确显示中文。

    注意：源码里不要出现字体不支持的符号（例如各种花式警示符），
    否则一旦这些字符被显示到界面上，同样会变成方框。当前所用字体的
    字符覆盖情况可用 fontTools 检查，详见仓库提交记录。
"""

import os

from kivy.app import App
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.switch import Switch
from kivy.graphics import Color, Rectangle, RoundedRectangle

# 核心逻辑（保持与旧版完全一致的调用方式）
from batch_renamer.core import generate_plan, undo_rename
from batch_renamer.operations import AddPrefix, AddSuffix, ReplaceText, InsertIndex

# Android 运行时权限申请（非 Android 平台导入失败时自动降级）
try:
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
    _IS_ANDROID = True
except Exception:  # pragma: no cover - 桌面端/CI 环境
    _IS_ANDROID = False


LOG_NAME = "rename_log.json"


# ================= 中文字体注册 =================
# Kivy 默认字体 Roboto 只有拉丁字母，中文会全部渲染成"带叉的空方框"。
# （源码注释里请勿出现字体本身不支持的符号，详见下方"源码字符约束"说明。）
# 解决方式：把仓库内 fonts/ 目录下的中文字体注册成 Kivy 的默认字体名
# 'Roboto'，这样所有控件（不区分是 Label / Button / TextInput）都会用它，
# 不需要在每个控件上单独写 font_name。
#
# 找不到字体时的降级策略：
#   直接跳过注册，界面仍能启动，只是中文会显示为方框 —— 比启动即崩溃好。
#   同时把原因记录下来，方便排查（APK 里字体没打进包是最可能的原因）。

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
# 候选字体按优先级排列。首选 .ttf（单字体文件）：
#   Kivy 使用 SDL2_ttf 加载字体，对「字体集合」（.ttc，一个文件里塞多个字重）
#   的支持并不总是可靠 —— 老版本 SDL2_ttf 会只认第一个字体，或者干脆报错。
#   .ttf 是单一 sfnt 字体，兼容性最好，因此排在第一位。
#   .ttc 版本仍然保留为次选（万一 ttf 被漏提交，还有它兜底）。
#   注意：本仓库当前只提交了 .ttf；.ttc 已删除以避免重复占用 ~4.9MB 体积
#   （经验证 TTF 与 TTC 第一个字重的 cmap 完全一致）。
FONT_CANDIDATES = (
    "WenQuanYiMicroHei.ttf",
    "WenQuanYiMicroHei.ttc",
    "NotoSansSC-Regular.otf",
    "SourceHanSansSC-Regular.otf",
)
_FONT_LOADED = None  # None=未尝试, str=成功路径, False=失败


def register_chinese_font():
    """把中文字体注册为 Kivy 的默认字体，返回是否成功。

    可重复调用（结果会缓存），因此在 App.build() 里调用是安全的。
    """
    global _FONT_LOADED
    if _FONT_LOADED is not None:
        return bool(_FONT_LOADED)

    for name in FONT_CANDIDATES:
        path = os.path.join(FONT_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            # 注册为 'Roboto' —— 覆盖 Kivy 的默认字体名，
            # 这样所有未显式指定 font_name 的控件都会自动使用它。
            LabelBase.register(name="Roboto", fn_regular=path)
            _FONT_LOADED = path
            return True
        except Exception as exc:  # pragma: no cover - 依赖运行环境
            print(f"[font] 注册中文字体失败 {path}: {exc}")
            continue

    _FONT_LOADED = False
    print(
        "[font] 未找到可用的中文字体，中文可能显示为方框。"
        f" 期望目录: {FONT_DIR}"
    )
    return False


# ================= 配色（现代浅色主题） =================
COLOR_BG = (0.945, 0.949, 0.961, 1)       # 页面背景（浅灰）
COLOR_CARD = (1, 1, 1, 1)                 # 卡片背景（纯白）
COLOR_TOPBAR = (0.153, 0.286, 0.541, 1)   # 顶部标题栏（深蓝）
COLOR_PRIMARY = (0.259, 0.522, 0.918, 1)  # 蓝（主色 / 预览）
COLOR_PRIMARY_D = (0.184, 0.404, 0.749, 1)
COLOR_SUCCESS = (0.180, 0.671, 0.427, 1)  # 绿（执行）
COLOR_SUCCESS_D = (0.129, 0.525, 0.325, 1)
COLOR_WARN = (0.902, 0.494, 0.153, 1)     # 橙（撤销）
COLOR_WARN_D = (0.729, 0.376, 0.098, 1)
COLOR_TEXT = (0.129, 0.137, 0.176, 1)     # 主文字
COLOR_MUTED = (0.451, 0.463, 0.514, 1)    # 次要文字
COLOR_LINE = (0.878, 0.886, 0.906, 1)     # 分割线
COLOR_INPUT = (0.965, 0.969, 0.980, 1)    # 输入框底色
COLOR_TERMINAL = (0.106, 0.122, 0.161, 1) # 结果区深色底
COLOR_TERMINAL_TX = (0.624, 0.878, 0.706, 1)  # 结果区绿字（终端风）

RADIUS = dp(10)


# ================= 绘图小工具 =================

def _draw_round(widget, rgba, radius=RADIUS):
    """给控件画一个圆角纯色背景，并随控件 pos/size 自动更新。"""
    with widget.canvas.before:
        color = Color(*rgba)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])

    def _update(*_):
        rect.pos = widget.pos
        rect.size = widget.size

    widget.bind(pos=_update, size=_update)
    return rect


def _draw_flat(widget, rgba):
    """给控件画一个直角纯色背景（用于整页底色这类大面积区域）。"""
    with widget.canvas.before:
        Color(*rgba)
        rect = Rectangle(pos=widget.pos, size=widget.size)

    def _update(*_):
        rect.pos = widget.pos
        rect.size = widget.size

    widget.bind(pos=_update, size=_update)
    return rect


def _bind_label(label, height=None, color=None):
    """让 Label 的文字在自身宽度内自动换行 / 对齐。

    Kivy 的 Label 必须显式设置 text_size 才会做对齐与换行，
    且 text_size 要跟随 width 变化，所以这里用 bind 挂上。
    """
    def _sync(w, *_):
        w.text_size = (w.width, None)

    label.bind(size=_sync)
    if height is not None:
        label.size_hint_y = None
        label.height = height
    if color is not None:
        label.color = color
    label.halign = "left"
    label.valign = "middle"
    return label


# ================= 自定义控件 =================

class Card(BoxLayout):
    """一张白色圆角卡片：自带内边距，用来分组放内容。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", [dp(14), dp(12), dp(14), dp(12)])
        kwargs.setdefault("spacing", dp(10))
        kwargs.setdefault("size_hint", (1, None))
        super().__init__(**kwargs)
        _draw_round(self, COLOR_CARD, RADIUS)


class RoundButton(Button):
    """圆角纯色按钮。

    Kivy 默认按钮自带一张贴图（background_normal / down），
    在深色或自定义配色下显得很突兀，这里清空贴图并手绘圆角背景。
    按下时自动换成加深色，给出触感反馈。
    """

    def __init__(self, text="", bg=COLOR_PRIMARY, bg_down=None, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("color", (1, 1, 1, 1))
        kwargs.setdefault("font_size", dp(15))
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(46))
        super().__init__(text=text, **kwargs)

        self._bg_normal = bg
        self._bg_down = bg_down or tuple(max(0.0, c - 0.12) for c in bg[:3]) + (bg[3],)

        # 手绘圆角背景：先建 Color + RoundedRectangle，再挂 pos/size 同步
        with self.canvas.before:
            self._color = Color(*bg)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size,
                                          radius=[RADIUS])

        def _sync(w, *_):
            self._rect.pos = w.pos
            self._rect.size = w.size

        # 只绑定一次，之后切换状态时直接改 Color 的 rgba（O(1)，无泄漏）
        self.bind(pos=_sync, size=_sync)
        self.bind(state=self._on_state)

    def _on_state(self, _widget, state):
        """state 在 normal / down 之间切换，同步背景色（只改颜色，不重建画布）。"""
        self._color.rgba = self._bg_down if state == "down" else self._bg_normal


class FieldInput(TextInput):
    """圆角浅灰底输入框，去掉 Kivy 默认的方框边框。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("font_size", dp(14))
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_active", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("foreground_color", COLOR_TEXT)
        kwargs.setdefault("cursor_color", COLOR_PRIMARY)
        kwargs.setdefault("hint_text_color", COLOR_MUTED)
        kwargs.setdefault("padding", [dp(10), dp(10), dp(10), dp(10)])
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(44))
        super().__init__(**kwargs)
        _draw_round(self, COLOR_INPUT, dp(8))


class LabeledField(BoxLayout):
    """「说明文字 + 控件」的竖排组合。

    窄屏上把说明放在控件上方，比挤在同一行更容易读，也不会压扁输入框。
    """

    def __init__(self, label_text, widget, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("spacing", dp(4))
        super().__init__(**kwargs)

        cap = Label(
            text=label_text,
            color=COLOR_MUTED,
            font_size=dp(12),
            size_hint=(1, None),
            height=dp(18),
        )
        _bind_label(cap)
        self.add_widget(cap)
        self.add_widget(widget)

        self.height = cap.height + widget.height + self.spacing


# ================= 主应用 =================

class BatchRenamerApp(App):
    def build(self):
        self.title = "批量重命名工具"

        # 最先注册中文字体 —— 必须早于任何控件的创建，
        # 否则已经创建的控件仍会沿用 Roboto（中文变豆腐块）。
        register_chinese_font()

        self.selected_folder = ""
        self.plan = None

        if _IS_ANDROID:
            self._request_android_permissions()

        # ================= 根布局 =================
        root = BoxLayout(orientation="vertical")
        _draw_flat(root, COLOR_BG)

        # ---------------- 顶部彩色标题栏 ----------------
        topbar = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(64),
            padding=[dp(16), dp(10), dp(16), dp(10)],
        )
        _draw_flat(topbar, COLOR_TOPBAR)

        app_title = Label(
            text="[b]批量重命名[/b]",
            markup=True,
            color=(1, 1, 1, 1),
            font_size=dp(20),
            size_hint=(1, None),
            height=dp(26),
        )
        _bind_label(app_title)
        topbar.add_widget(app_title)

        app_sub = Label(
            text="按规则批量整理你的文件",
            color=(0.78, 0.84, 0.94, 1),
            font_size=dp(12),
            size_hint=(1, None),
            height=dp(18),
        )
        _bind_label(app_sub)
        topbar.add_widget(app_sub)
        root.add_widget(topbar)

        # ---------------- 可滚动内容区 ----------------
        page = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(14), dp(12), dp(20)],
            spacing=dp(14),
            size_hint=(1, None),
        )
        page.bind(minimum_height=page.setter("height"))

        scroll = ScrollView(size_hint=(1, 1), bar_width=dp(2))
        scroll.add_widget(page)
        root.add_widget(scroll)

        # ================= 卡片 1：文件夹选择 =================
        folder_card = Card()

        folder_card.add_widget(self._section_title("文件夹"))

        self.folder_label = Label(
            text="尚未选择文件夹",
            color=COLOR_TEXT,
            font_size=dp(14),
            size_hint=(1, None),
            height=dp(34),
            shorten=True,
            shorten_from="left",
        )
        _bind_label(self.folder_label, height=dp(34))
        folder_card.add_widget(self.folder_label)

        btn_select = RoundButton(
            text="选择文件夹",
            bg=COLOR_PRIMARY,
            bg_down=COLOR_PRIMARY_D,
        )
        btn_select.bind(on_release=self.open_file_chooser)
        folder_card.add_widget(btn_select)

        folder_card.height = dp(48) + dp(34) + dp(46) + dp(24) + dp(20)
        page.add_widget(folder_card)

        # ================= 卡片 2：重命名规则 =================
        ops_card = Card()
        ops_card.add_widget(self._section_title("重命名规则"))

        # --- 前缀 ---
        self.prefix_input = FieldInput(hint_text="例如：2024_")
        ops_card.add_widget(LabeledField("在前缀添加", self.prefix_input))

        ops_card.add_widget(self._divider())

        # --- 后缀 ---
        self.suffix_input = FieldInput(hint_text="例如：_final")
        ops_card.add_widget(LabeledField("在后缀添加", self.suffix_input))

        ops_card.add_widget(self._divider())

        # --- 替换 ---
        self.find_input = FieldInput(hint_text="要查找的文字")
        ops_card.add_widget(LabeledField("查找", self.find_input))

        self.replace_input = FieldInput(hint_text="替换为（留空即删除）")
        ops_card.add_widget(LabeledField("替换", self.replace_input))

        ops_card.add_widget(self._divider())

        # --- 插入序号 ---
        index_head = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(48),
            spacing=dp(8),
        )
        idx_label = Label(
            text="插入序号",
            color=COLOR_TEXT,
            font_size=dp(14),
            size_hint=(1, 1),
        )
        _bind_label(idx_label)
        index_head.add_widget(idx_label)

        self.index_state = Label(
            text="关",
            color=COLOR_MUTED,
            font_size=dp(13),
            size_hint=(None, 1),
            width=dp(30),
            halign="right",
            valign="middle",
        )
        self.index_state.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
        index_head.add_widget(self.index_state)

        self.index_switch = Switch(active=False, size_hint=(None, None),
                                   size=(dp(52), dp(32)))
        self.index_switch.bind(active=self._on_index_toggle)
        index_head.add_widget(self.index_switch)
        ops_card.add_widget(index_head)

        # --- 序号参数（开关关闭时禁用） ---
        self.index_params = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(64),
            spacing=dp(10),
        )

        self.start_input = FieldInput(text="1")
        self.start_input.input_filter = "int"
        wrap_start = LabeledField("起始", self.start_input)

        self.digits_input = FieldInput(text="2")
        self.digits_input.input_filter = "int"
        wrap_digits = LabeledField("位数", self.digits_input)

        self.index_params.add_widget(wrap_start)
        self.index_params.add_widget(wrap_digits)
        ops_card.add_widget(self.index_params)

        ops_card.height = dp(48) + dp(78) + dp(1) + dp(78) + dp(1) + dp(66) + dp(66) + dp(1) \
            + dp(48) + dp(64) + dp(24) + dp(7) * dp(10)
        page.add_widget(ops_card)

        self._set_index_params_enabled(False)

        # ================= 卡片 3：操作按钮 =================
        btn_card = Card()

        btn_preview = RoundButton(text="预览", bg=COLOR_PRIMARY, bg_down=COLOR_PRIMARY_D)
        btn_preview.bind(on_release=self.preview)
        btn_card.add_widget(btn_preview)

        btn_exec = RoundButton(text="执行重命名", bg=COLOR_SUCCESS, bg_down=COLOR_SUCCESS_D)
        btn_exec.bind(on_release=self.execute)
        btn_card.add_widget(btn_exec)

        btn_undo = RoundButton(text="撤销上次", bg=COLOR_WARN, bg_down=COLOR_WARN_D)
        btn_undo.bind(on_release=self.undo)
        btn_card.add_widget(btn_undo)

        tip = Label(
            text="建议先「预览」确认无误，再「执行重命名」。",
            color=COLOR_MUTED,
            font_size=dp(12),
            size_hint=(1, None),
            height=dp(20),
        )
        _bind_label(tip)
        btn_card.add_widget(tip)

        btn_card.height = dp(46) * 3 + dp(20) + dp(30) + dp(24)
        page.add_widget(btn_card)

        # ================= 卡片 4：结果 =================
        result_card = Card()
        result_card.add_widget(self._section_title("执行结果"))

        self.result_label = Label(
            text="（尚未执行）",
            color=COLOR_TERMINAL_TX,
            font_size=dp(12),
            size_hint=(1, None),
            height=dp(120),
            halign="left",
            valign="top",
        )
        self.result_label.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))

        self.result_scroll = ScrollView(size_hint=(1, None), height=dp(160),
                                        bar_width=dp(2))
        holder = BoxLayout(orientation="vertical", size_hint=(1, None), padding=dp(10))
        _draw_round(holder, COLOR_TERMINAL, dp(8))
        holder.bind(minimum_height=holder.setter("height"))
        holder.add_widget(self.result_label)

        # 让 Label 高度跟随内容增长，容器随之撑开
        self.result_label.bind(
            texture_size=lambda w, val: setattr(w, "height", max(dp(120), val[1] + dp(4)))
        )
        self.result_scroll.add_widget(holder)
        result_card.add_widget(self.result_scroll)

        result_card.height = dp(48) + dp(160) + dp(24) + dp(20)
        page.add_widget(result_card)

        return root

    # ================= UI 小工具 =================

    def _section_title(self, text):
        """卡片内的分区标题。"""
        lbl = Label(
            text=f"[b]{text}[/b]",
            markup=True,
            color=COLOR_TEXT,
            font_size=dp(15),
            size_hint=(1, None),
            height=dp(28),
        )
        _bind_label(lbl)
        return lbl

    def _divider(self):
        """一条 1dp 的分割线。"""
        line = BoxLayout(size_hint=(1, None), height=dp(1))
        _draw_flat(line, COLOR_LINE)
        return line

    # ================= 交互逻辑 =================

    def _on_index_toggle(self, _switch, active):
        """序号开关联动：更新状态文字 + 启用/禁用参数框。"""
        self.index_state.text = "开" if active else "关"
        self.index_state.color = COLOR_SUCCESS if active else COLOR_MUTED
        self._set_index_params_enabled(active)

    def _set_index_params_enabled(self, enabled):
        """参数框启用/置灰，给出「不可用」的视觉反馈。"""
        opacity = 1.0 if enabled else 0.4
        for w in (self.start_input, self.digits_input):
            w.disabled = not enabled
            w.opacity = opacity

    # ================= 权限 =================

    def _request_android_permissions(self):
        """申请存储相关运行时权限。"""
        try:
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.MANAGE_EXTERNAL_STORAGE,
            ])
        except Exception:
            pass

    def _check_manage_storage(self):
        """兼容旧逻辑：检查是否有「所有文件访问」权限。

        返回 True 表示可以继续；返回 False 时会弹出引导框，
        让用户去系统设置里手动开启 MANAGE_EXTERNAL_STORAGE。
        """
        if not _IS_ANDROID:
            return True
        try:
            Environment = autoclass("android.os.Environment")
            if Environment.isExternalStorageManager():
                return True

            content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
            msg = Label(
                text="需要「所有文件访问」权限才能操作任意文件夹。\n请到系统设置中为本应用开启该权限。",
                halign="left",
                valign="middle",
            )
            msg.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
            content.add_widget(msg)

            popup = Popup(title="缺少权限", content=content,
                          size_hint=(0.85, 0.4))

            def open_settings(_):
                try:
                    Intent = autoclass("android.content.Intent")
                    Settings = autoclass("android.provider.Settings")
                    Uri = autoclass("android.net.Uri")
                    PythonActivity = autoclass("org.kivy.android.PythonActivity")
                    intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                    intent.setData(Uri.parse("package:" + PythonActivity.mActivity.getPackageName()))
                    PythonActivity.mActivity.startActivity(intent)
                except Exception:
                    pass
                popup.dismiss()

            btn = RoundButton(text="去设置", bg=COLOR_PRIMARY, bg_down=COLOR_PRIMARY_D)
            btn.bind(on_release=open_settings)
            content.add_widget(btn)
            popup.open()
            return False
        except Exception:
            # 无法判断时放行，避免误拦用户
            return True

    # ================= 选择文件夹 =================

    def open_file_chooser(self, instance):
        """弹出文件选择器，选一个目录。"""
        if not self._check_manage_storage():
            return

        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(6))
        chooser = FileChooserListView(path="/storage/emulated/0",
                                      dirselect=True)
        content.add_widget(chooser)

        btns = BoxLayout(orientation="horizontal", size_hint=(1, None),
                         height=dp(46), spacing=dp(8))
        btn_ok = RoundButton(text="选择此文件夹", bg=COLOR_PRIMARY, bg_down=COLOR_PRIMARY_D)
        btn_cancel = RoundButton(text="取消", bg=COLOR_MUTED, bg_down=COLOR_TEXT)

        popup = Popup(title="选择文件夹", content=content, size_hint=(0.95, 0.9))
        btn_ok.bind(on_release=lambda *_: self.select_folder(chooser.path, popup))
        btn_cancel.bind(on_release=lambda *_: popup.dismiss())

        btns.add_widget(btn_ok)
        btns.add_widget(btn_cancel)
        content.add_widget(btns)
        popup.open()

    def select_folder(self, path, popup):
        """确认选择文件夹，刷新界面上的路径文字。"""
        self.selected_folder = path or ""
        self.folder_label.text = self.selected_folder or "尚未选择文件夹"
        self.result_label.text = "（尚未执行）"
        self.plan = None
        popup.dismiss()

    # ================= 文件与操作 =================

    def get_files_in_folder(self):
        """列出目录下的普通文件（隐藏文件跳过）。"""
        if not self.selected_folder or not os.path.isdir(self.selected_folder):
            return []
        try:
            names = os.listdir(self.selected_folder)
        except OSError:
            return []
        return sorted(
            n for n in names
            if not n.startswith(".") and os.path.isfile(os.path.join(self.selected_folder, n))
        )

    def build_operations(self):
        """按界面输入拼出操作列表（与旧版逻辑一致）。"""
        ops = []
        if self.prefix_input.text:
            ops.append(AddPrefix(self.prefix_input.text))
        if self.suffix_input.text:
            ops.append(AddSuffix(self.suffix_input.text))
        if self.find_input.text:
            ops.append(ReplaceText(self.find_input.text, self.replace_input.text))
        if self.index_switch.active:
            try:
                start = int(self.start_input.text or "1")
            except ValueError:
                start = 1
            try:
                digits = int(self.digits_input.text or "2")
            except ValueError:
                digits = 2
            ops.append(InsertIndex(start=start, digits=digits))
        return ops

    def log_path(self):
        """日志文件固定放在所选文件夹下（按目录隔离）。"""
        if not self.selected_folder:
            return ""
        return os.path.join(self.selected_folder, LOG_NAME)

    # ================= 三个主操作 =================

    def preview(self, instance):
        """生成重命名计划并展示「原名 -> 新名」。"""
        if not self.selected_folder:
            self.show_message("请先选择文件夹")
            return

        files = self.get_files_in_folder()
        if not files:
            self.show_message("文件夹里没有可处理的文件")
            return

        ops = self.build_operations()
        if not ops:
            self.show_message("请至少设置一个操作")
            return

        self.plan = generate_plan(files, ops, base_dir=self.selected_folder)

        lines = []
        changed = 0
        for old, new in self.plan.pairs.items():
            old_n = os.path.basename(old)
            new_n = os.path.basename(new)
            if old_n != new_n:
                lines.append(f"{old_n}  ->  {new_n}")
                changed += 1

        if not lines:
            self.result_label.text = "没有文件需要重命名"
            return

        if self.plan.has_conflicts():
            lines.append("")
            lines.append("!! 警告：存在重命名冲突！")
            for name in self.plan.conflicts():
                lines.append(f"  冲突: {os.path.basename(name)}")

        lines.append("")
        lines.append(f"共 {changed} 项变更")
        self.result_label.text = "\n".join(lines)

    def execute(self, instance):
        """执行重命名（依赖 preview 生成的计划）。"""
        if self.plan is None:
            self.show_message("请先预览")
            return
        if self.plan.has_conflicts():
            self.show_message("存在冲突，无法执行")
            return
        try:
            self.plan.execute(log_path=self.log_path())
            self.result_label.text = "✓ 重命名完成"
            self.plan = None
        except Exception as e:
            self.show_message(f"执行失败: {e}")

    def undo(self, instance):
        """按日志撤销上一次重命名。"""
        if not self.selected_folder:
            self.show_message("请先选择文件夹")
            return
        try:
            undo_rename(log_path=self.log_path())
            self.result_label.text = "✓ 已撤销"
            self.plan = None
        except FileNotFoundError:
            self.show_message("这个文件夹没有可撤销的记录")
        except Exception as e:
            self.show_message(f"撤销失败: {e}")

    def show_message(self, message):
        popup = Popup(
            title="提示",
            content=Label(text=message),
            size_hint=(0.8, 0.4),
        )
        popup.open()


if __name__ == "__main__":
    BatchRenamerApp().run()
