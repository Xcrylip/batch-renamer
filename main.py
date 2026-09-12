import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.switch import Switch

# 核心逻辑
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


class BatchRenamerApp(App):
    def build(self):
        self.title = "批量重命名工具"
        self.selected_folder = ""
        self.plan = None

        if _IS_ANDROID:
            self._request_android_permissions()

        root = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # ---- 文件夹选择 ----
        self.folder_label = Label(text="未选择文件夹", size_hint=(1, 0.08))
        root.add_widget(self.folder_label)

        btn_select = Button(text="选择文件夹", size_hint=(1, 0.1))
        btn_select.bind(on_press=self.open_file_chooser)
        root.add_widget(btn_select)

        # ---- 操作设置 ----
        ops_layout = BoxLayout(orientation="vertical", spacing=5, size_hint=(1, 0.45))

        def row(label_text, widget, label_w=0.2):
            box = BoxLayout(orientation="horizontal", size_hint=(1, None), height=40)
            box.add_widget(Label(text=label_text, size_hint=(label_w, 1)))
            box.add_widget(widget)
            return box

        # 前缀
        self.prefix_input = TextInput(multiline=False, size_hint=(0.8, 1))
        ops_layout.add_widget(row("前缀:", self.prefix_input))

        # 后缀
        self.suffix_input = TextInput(multiline=False, size_hint=(0.8, 1))
        ops_layout.add_widget(row("后缀:", self.suffix_input))

        # 替换
        replace_box = BoxLayout(orientation="horizontal", size_hint=(1, None), height=40)
        replace_box.add_widget(Label(text="替换:", size_hint=(0.2, 1)))
        self.replace_old = TextInput(multiline=False, hint_text="旧文本", size_hint=(0.4, 1))
        self.replace_new = TextInput(multiline=False, hint_text="新文本", size_hint=(0.4, 1))
        replace_box.add_widget(self.replace_old)
        replace_box.add_widget(self.replace_new)
        ops_layout.add_widget(replace_box)

        # 插入序号（开关 + 起始值 + 位数）
        self.index_switch = Switch(active=False, size_hint=(1, 1))
        index_toggle = BoxLayout(orientation="horizontal", size_hint=(1, None), height=40)
        index_toggle.add_widget(Label(text="插入序号:", size_hint=(0.2, 1)))
        index_toggle.add_widget(self.index_switch)
        ops_layout.add_widget(index_toggle)

        index_param_box = BoxLayout(orientation="horizontal", size_hint=(1, None), height=40, spacing=5)
        index_param_box.add_widget(Label(text="起始:", size_hint=(0.15, 1)))
        self.index_start = TextInput(text="1", multiline=False, input_filter="int", size_hint=(0.35, 1))
        index_param_box.add_widget(self.index_start)
        index_param_box.add_widget(Label(text="位数:", size_hint=(0.15, 1)))
        self.index_digits = TextInput(text="2", multiline=False, input_filter="int", size_hint=(0.35, 1))
        index_param_box.add_widget(self.index_digits)
        ops_layout.add_widget(index_param_box)

        root.add_widget(ops_layout)

        # ---- 按钮 ----
        btn_layout = BoxLayout(orientation="horizontal", spacing=5, size_hint=(1, 0.1))
        btn_preview = Button(text="预览")
        btn_preview.bind(on_press=self.preview)
        btn_execute = Button(text="执行")
        btn_execute.bind(on_press=self.execute)
        btn_undo = Button(text="撤销")
        btn_undo.bind(on_press=self.undo)
        btn_layout.add_widget(btn_preview)
        btn_layout.add_widget(btn_execute)
        btn_layout.add_widget(btn_undo)
        root.add_widget(btn_layout)

        # ---- 结果区 ----
        self.result_label = Label(text="", size_hint=(1, None), halign="left", valign="top")
        self.result_label.bind(
            width=lambda *x: setattr(self.result_label, "text_size", (self.result_label.width, None))
        )
        self.result_label.bind(texture_size=self.result_label.setter("size"))
        scroll = ScrollView(size_hint=(1, 0.35))
        scroll.add_widget(self.result_label)
        root.add_widget(scroll)

        return root

    # ---------------- 权限 ----------------

    def _request_android_permissions(self):
        """申请存储权限，并引导用户开启「所有文件访问」（Android 11+ 必须）。"""
        try:
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.MANAGE_EXTERNAL_STORAGE,
            ])
        except Exception:
            pass

    def _check_manage_storage(self):
        """检查 MANAGE_EXTERNAL_STORAGE 是否已授予，未授予则引导去设置。"""
        if not _IS_ANDROID:
            return True
        try:
            Environment = autoclass("android.os.Environment")
            if Environment.isExternalStorageManager():
                return True
        except Exception:
            return True  # 判断失败就不拦，让后续操作自己报错

        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        content.add_widget(Label(
            text="需要「所有文件访问」权限\n才能读取和重命名文件。\n\n请在设置中授予本应用该权限。"
        ))
        btn = Button(text="去设置", size_hint=(1, 0.4))

        popup = Popup(title="缺少权限", content=content, size_hint=(0.85, 0.5))

        def open_settings(_):
            popup.dismiss()
            try:
                Intent = autoclass("android.content.Intent")
                Settings = autoclass("android.provider.Settings")
                Uri = autoclass("android.net.Uri")
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                activity = PythonActivity.mActivity
                intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                intent.setData(Uri.parse("package:" + activity.getPackageName()))
                activity.startActivity(intent)
            except Exception as e:
                self.show_message(f"无法打开设置: {e}")

        btn.bind(on_press=open_settings)
        content.add_widget(btn)
        popup.open()
        return False

    # ---------------- 文件夹选择 ----------------

    def open_file_chooser(self, instance):
        if not self._check_manage_storage():
            return

        # 默认从外部存储根目录开始，方便用户直接看到相册/下载
        start_path = "/storage/emulated/0"
        if not os.path.isdir(start_path):
            start_path = os.path.expanduser("~")

        content = BoxLayout(orientation="vertical")
        filechooser = FileChooserListView(path=start_path, dirselect=True)
        content.add_widget(filechooser)
        btn_close = Button(text="选择此文件夹", size_hint=(1, 0.1))
        content.add_widget(btn_close)

        popup = Popup(title="选择文件夹", content=content, size_hint=(0.95, 0.95))
        btn_close.bind(on_press=lambda x: self.select_folder(filechooser.path, popup))
        popup.open()

    def select_folder(self, path, popup):
        self.selected_folder = path
        self.folder_label.text = f"已选择: {path}"
        self.plan = None
        popup.dismiss()

    # ---------------- 工具方法 ----------------

    def get_files_in_folder(self):
        """获取所选目录下的所有文件（不递归、不包含隐藏文件）。"""
        if not self.selected_folder:
            return []
        try:
            return [
                f
                for f in sorted(os.listdir(self.selected_folder))
                if not f.startswith(".")
                and os.path.isfile(os.path.join(self.selected_folder, f))
            ]
        except Exception as e:
            self.show_message(f"读取文件夹失败: {e}")
            return []

    def build_operations(self):
        ops = []
        if self.prefix_input.text:
            ops.append(AddPrefix(self.prefix_input.text))
        if self.suffix_input.text:
            ops.append(AddSuffix(self.suffix_input.text))
        if self.replace_old.text:
            ops.append(ReplaceText(self.replace_old.text, self.replace_new.text))
        if self.index_switch.active:
            try:
                start = int(self.index_start.text or "1")
            except ValueError:
                start = 1
            try:
                digits = int(self.index_digits.text or "0")
            except ValueError:
                digits = 0
            ops.append(InsertIndex(start=start, digits=digits))
        return ops

    def log_path(self):
        """撤销日志放在所选目录下，避免多目录互相覆盖。"""
        return os.path.join(self.selected_folder, LOG_NAME)

    # ---------------- 三大操作 ----------------

    def preview(self, instance):
        if not self.selected_folder:
            self.show_message("请先选择文件夹")
            return

        files = self.get_files_in_folder()
        if not files:
            self.show_message("文件夹中没有文件")
            return

        ops = self.build_operations()
        if not ops:
            self.show_message("请至少设置一个操作")
            return

        # 传 base_dir，产出「绝对路径 -> 绝对路径」的计划，无需 chdir
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
            lines.append("\n⚠ 警告：存在重命名冲突！")
            for name in self.plan.conflicts():
                lines.append(f"  冲突: {os.path.basename(name)}")

        lines.append(f"\n共 {changed} 项变更")
        self.result_label.text = "\n".join(lines)

    def execute(self, instance):
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