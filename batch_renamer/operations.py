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
    def __init__(self, start: int = 1, step: int = 1, digits: int = 0, position: str = "end", separator: str = "_"):
        """
        :param start: 起始序号
        :param step: 序号增量
        :param digits: 序号最小位数（不足补零），0 表示不补零
        :param position: 插入位置，'start' 表示文件名开头，'end' 表示扩展名前
        :param separator: 序号与文件名之间的分隔符
        """
        self.start = start
        self.step = step
        self.digits = digits
        self.position = position
        self.separator = separator
        self._counter = start  # 内部计数器，每个文件调用一次递增

    def apply(self, filename: str) -> str:
        index = self._counter
        self._counter += self.step
        index_str = str(index).zfill(self.digits) if self.digits > 0 else str(index)
        name, ext = os.path.splitext(filename)
        if self.position == "start":
            return f"{index_str}{self.separator}{name}{ext}"
        else:  # 默认 end，在扩展名前
            return f"{name}{self.separator}{index_str}{ext}"