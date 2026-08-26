import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.checkbox import CheckBox
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivy.core.window import Window

# 导入核心模块（假设项目结构正确）
from batch_renamer.core import generate_plan, undo_rename
from batch_renamer.operations import AddPrefix, AddSuffix, ReplaceText

class BatchRenamerApp(App):
    def build(self):
        self.title = "批量重命名工具"
        self.selected_folder = ""
        self.plan = None

        # 主布局
        self.main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # 顶部：文件夹选择
        self.folder_label = Label(text="未选择文件夹", size_hint=(1, 0.1))
        self.main_layout.add_widget(self.folder_label)

        btn_select = Button(text="选择文件夹", size_hint=(1, 0.1))
        btn_select.bind(on_press=self.open_file_chooser)
        self.main_layout.add_widget(btn_select)

        # 操作设置区域
        ops_layout = BoxLayout(orientation='vertical', spacing=5, size_hint=(1, 0.4))

        # 前缀
        prefix_box = BoxLayout(orientation='horizontal', size_hint=(1, None), height=40)
        prefix_box.add_widget(Label(text="前缀:", size_hint=(0.2, 1)))
        self.prefix_input = TextInput(text="", multiline=False, size_hint=(0.8, 1))
        prefix_box.add_widget(self.prefix_input)
        ops_layout.add_widget(prefix_box)

        # 后缀
        suffix_box = BoxLayout(orientation='horizontal', size_hint=(1, None), height=40)
        suffix_box.add_widget(Label(text="后缀:", size_hint=(0.2, 1)))
        self.suffix_input = TextInput(text="", multiline=False, size_hint=(0.8, 1))
        suffix_box.add_widget(self.suffix_input)
        ops_layout.add_widget(suffix_box)

        # 替换
        replace_box = BoxLayout(orientation='horizontal', size_hint=(1, None), height=40)
        replace_box.add_widget(Label(text="替换:", size_hint=(0.2, 1)))
        self.replace_old = TextInput(text="", multiline=False, hint_text="旧文本", size_hint=(0.4, 1))
        self.replace_new = TextInput(text="", multiline=False, hint_text="新文本", size_hint=(0.4, 1))
        replace_box.add_widget(self.replace_old)
        replace_box.add_widget(self.replace_new)
        ops_layout.add_widget(replace_box)

        self.main_layout.add_widget(ops_layout)

        # 按钮区域
        btn_layout = BoxLayout(orientation='horizontal', spacing=5, size_hint=(1, 0.1))
        btn_preview = Button(text="预览")
        btn_preview.bind(on_press=self.preview)
        btn_execute = Button(text="执行")
        btn_execute.bind(on_press=self.execute)
        btn_undo = Button(text="撤销")
        btn_undo.bind(on_press=self.undo)
        btn_layout.add_widget(btn_preview)
        btn_layout.add_widget(btn_execute)
        btn_layout.add_widget(btn_undo)
        self.main_layout.add_widget(btn_layout)

        # 结果显示区域（可滚动）
        self.result_label = Label(text="", size_hint=(1, 0.4), halign='left', valign='top')
        self.result_label.bind(size=self.result_label.setter('text_size'))
        scroll = ScrollView(size_hint=(1, 0.4))
        scroll.add_widget(self.result_label)
        self.main_layout.add_widget(scroll)

        return self.main_layout

    def open_file_chooser(self, instance):
        """打开系统文件选择器让用户选择文件夹"""
        content = BoxLayout(orientation='vertical')
        filechooser = FileChooserListView(dirselect=True)  # 允许选择目录
        content.add_widget(filechooser)
        btn_close = Button(text="选择此文件夹", size_hint=(1, 0.1))
        content.add_widget(btn_close)

        popup = Popup(title="选择文件夹", content=content, size_hint=(0.9, 0.9))
        btn_close.bind(on_press=lambda x: self.select_folder(filechooser.path, popup))
        popup.open()

    def select_folder(self, path, popup):
        """处理选中的文件夹"""
        self.selected_folder = path
        self.folder_label.text = f"已选择: {path}"
        popup.dismiss()

    def get_files_in_folder(self):
        """获取所选文件夹中的所有文件（不递归）"""
        if not self.selected_folder:
            return []
        try:
            files = [f for f in os.listdir(self.selected_folder)
                     if os.path.isfile(os.path.join(self.selected_folder, f))]
            return files
        except Exception as e:
            self.show_message(f"读取文件夹失败: {e}")
            return []

    def build_operations(self):
        """根据用户输入构建操作列表"""
        ops = []
        if self.prefix_input.text:
            ops.append(AddPrefix(self.prefix_input.text))
        if self.suffix_input.text:
            ops.append(AddSuffix(self.suffix_input.text))
        if self.replace_old.text or self.replace_new.text:
            # 如果只填了一个，另一个默认为空
            old = self.replace_old.text
            new = self.replace_new.text
            ops.append(ReplaceText(old, new))
        return ops

    def preview(self, instance):
        """预览重命名计划"""
        files = self.get_files_in_folder()
        if not files:
            self.show_message("文件夹中没有文件")
            return
        ops = self.build_operations()
        if not ops:
            self.show_message("请至少设置一个操作")
            return

        # 切换到目标目录，以便计划中使用相对文件名
        original_dir = os.getcwd()
        os.chdir(self.selected_folder)
        self.plan = generate_plan(files, ops)
        os.chdir(original_dir)

        # 显示预览
        lines = []
        for old, new in self.plan.pairs.items():
            lines.append(f"{old}  ->  {new}")
        if self.plan.has_conflicts():
            lines.append("\n警告：存在重命名冲突！")
            for name in self.plan.conflicts():
                lines.append(f"重复: {name}")
        self.result_label.text = "\n".join(lines)

    def execute(self, instance):
        """执行重命名"""
        if self.plan is None:
            self.show_message("请先预览")
            return
        if self.plan.has_conflicts():
            self.show_message("存在冲突，无法执行")
            return
        try:
            # 切换到目标目录执行
            original_dir = os.getcwd()
            os.chdir(self.selected_folder)
            self.plan.execute(log_path="rename_log.json")
            os.chdir(original_dir)
            self.result_label.text = "重命名完成！"
            self.plan = None  # 清空计划
        except Exception as e:
            self.show_message(f"执行失败: {e}")

    def undo(self, instance):
        """撤销上次操作"""
        if not self.selected_folder:
            self.show_message("请先选择文件夹")
            return
        try:
            original_dir = os.getcwd()
            os.chdir(self.selected_folder)
            undo_rename(log_path="rename_log.json")
            os.chdir(original_dir)
            self.result_label.text = "撤销完成"
        except Exception as e:
            self.show_message(f"撤销失败: {e}")

    def show_message(self, message):
        """弹窗显示消息"""
        popup = Popup(title="提示",
                      content=Label(text=message),
                      size_hint=(0.8, 0.4))
        popup.open()

if __name__ == "__main__":
    BatchRenamerApp().run()