from abc import ABC, abstractmethod
import os

class Operation(ABC):
    """所有重命名操作的基类"""
    @abstractmethod
    def apply(self, filename: str) -> str:
        pass

    def __repr__(self):
        return self.__class__.__name__

class AddPrefix(Operation):
    """在文件名前添加前缀"""
    def __init__(self, prefix: str):
        self.prefix = prefix

    def apply(self, filename: str) -> str:
        return self.prefix + filename

class AddSuffix(Operation):
    """在扩展名前添加后缀（默认分隔符为下划线）"""
    def __init__(self, suffix: str, separator: str = "_"):
        self.suffix = suffix
        self.separator = separator

    def apply(self, filename: str) -> str:
        name, ext = os.path.splitext(filename)
        return f"{name}{self.separator}{self.suffix}{ext}"

class ReplaceText(Operation):
    """替换文件名中的文本"""
    def __init__(self, old: str, new: str):
        self.old = old
        self.new = new

    def apply(self, filename: str) -> str:
        return filename.replace(self.old, self.new)

class InsertIndex(Operation):
    """在指定位置插入序号，支持自定义起始值、步长、位数、位置（开始或结尾）"""

    def __init__(self, start: int = 1, step: int = 1, digits: int = 0,
                 position: str = "end", separator: str = "_",
                 adaptive: bool = True):
        """
        :param start: 起始序号
        :param step: 序号增量
        :param digits: 序号最小位数（不足补零），0 表示不补零
        :param position: 插入位置，'start' 表示文件名开头，'end' 表示扩展名前
        :param separator: 序号与文件名之间的分隔符
        :param adaptive: 数字变长时是否自动少补一个前导零
            True  → 总宽度固定为 digits：009 → 010
            False → 前导零个数固定：009 → 0010
        """
        self.start = start
        self.step = step
        self.digits = digits
        self.position = position
        self.separator = separator
        self.adaptive = adaptive
        self._counter = start  # 内部计数器，每个文件调用一次递增

    def reset(self) -> None:
        """重置内部计数器。

        重要：每次生成新的重命名计划前必须调用，否则同一个操作对象
        被复用时（例如用户连续点两次「预览」）计数器会继续累加，
        导致预览结果与执行结果不一致。
        """
        self._counter = self.start

    def apply(self, filename: str) -> str:
        index = self._counter
        self._counter += self.step
        index_str = format_index(index, self.digits, self.adaptive)
        name, ext = os.path.splitext(filename)
        if self.position == "start":
            return f"{index_str}{self.separator}{name}{ext}"
        else:  # 默认 end，在扩展名前
            return f"{name}{self.separator}{index_str}{ext}"


# =====================================================================
# 补零 / 序号格式化
# =====================================================================
def format_index(value: int, digits: int = 0, adaptive: bool = True) -> str:
    """把序号格式化成字符串，补零规则由调用方传入。

    :param digits: 补零后的总位数。0/1 表示不补零，01 表示补 1 个零，
        001 表示补 2 个零（也就是 digits = 输入字符串的长度）。
    :param adaptive: 数字变长后是否自动少补一个前导零。
        True  → 总宽度固定（009 → 010），这是最符合直觉的写法；
        False → 前导零个数固定（009 → 0010），即「一直保留 2 个零」。
    """
    text = str(int(value))
    if digits is None or int(digits) <= 0:
        return text
    digits = int(digits)
    if adaptive:
        return text.zfill(digits)
    return "0" * max(digits - 1, 0) + text


def index_to_letters(value: int, start: int = 1) -> str:
    """把序号转成字母串：1→a、2→b、…、26→z、27→aa、28→ab。"""
    n = int(value) - int(start) + 1
    if n < 1:
        n = 1
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(ord("a") + r) + out
    return out


def split_name_parts(filename: str):
    """把文件名拆成 (文字部分, 数字部分, 扩展名)。

    只在「保留原文」模式下使用：从第一个数字开始切分，
    例如 "旅行照片2024.png" → ("旅行照片", "2024", ".png")。
    """
    stem, ext = os.path.splitext(filename)
    i = 0
    while i < len(stem) and not stem[i].isdigit():
        i += 1
    text_part = stem[:i]
    digit_part = "".join(ch for ch in stem[i:] if ch.isdigit())
    return text_part, digit_part, ext


class SegmentRename(Operation):
    """分段重命名：把文件名整体写成「文字区 + 数字区」，扩展名不动。

    和别的操作不同，它不去「猜」原文件名该怎么拆，而是两个区各自独立
    选择一种模式：

    * 文字区（字母 / 文字）
        - ``keep``  → 保留原文里的文字部分（第一个数字之前的那一段）
        - ``seq``   → 按顺序生成字母：a、b、c…、z、aa
        - ``fixed`` → 使用固定文字
    * 数字区
        - ``keep``  → 保留原文里的数字部分
        - ``seq``   → 按起始值 / 步长 / 补零规则编号
        - ``fixed`` → 使用固定数字

    组合示例（start=1、step=1、digits=0）::

        文字区 seq + 数字区 seq       → a1, b2, c3, d4
        文字区 fixed("图片") + 数字 seq → 图片1, 图片2, 图片3
        文字区 seq + 数字区 keep      → a1, b2（数字来自原文件名）
    """

    def __init__(self, text_mode: str = "keep", text_fixed: str = "",
                 text_start: int = 1, text_step: int = 1,
                 digit_mode: str = "seq", digit_fixed: str = "",
                 start: int = 1, step: int = 1,
                 digits: int = 0, adaptive: bool = True,
                 separator: str = ""):
        self.text_mode = text_mode if text_mode in ("keep", "seq", "fixed") else "keep"
        self.text_fixed = text_fixed or ""
        self.text_start = int(text_start)
        self.text_step = int(text_step) if int(text_step) else 1
        self.digit_mode = digit_mode if digit_mode in ("keep", "seq", "fixed") else "seq"
        self.digit_fixed = digit_fixed or ""
        self.start = int(start)
        self.step = int(step) if int(step) else 1
        self.digits = int(digits)
        self.adaptive = bool(adaptive)
        self.separator = separator or ""
        self._n = 0  # 已经处理过多少个文件（从 0 开始）

    def reset(self) -> None:
        """每次生成新计划前必须重置，否则连点两次「预览」结果会漂移。"""
        self._n = 0

    def apply(self, filename: str) -> str:
        n = self._n
        self._n += 1
        text_part, digit_part, ext = split_name_parts(filename)

        if self.text_mode == "seq":
            text_out = index_to_letters(self.text_start + n * self.text_step)
        elif self.text_mode == "fixed":
            text_out = self.text_fixed
        else:
            text_out = text_part

        if self.digit_mode == "seq":
            digit_out = format_index(self.start + n * self.step,
                                     self.digits, self.adaptive)
        elif self.digit_mode == "fixed":
            digit_out = self.digit_fixed
        else:
            digit_out = digit_part

        if text_out and digit_out:
            return f"{text_out}{self.separator}{digit_out}{ext}"
        # 有一区为空时不再插分隔符，避免出现「a_」这种多余符号
        return f"{text_out}{digit_out}{ext}"