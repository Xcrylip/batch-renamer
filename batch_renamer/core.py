import os
import json
from typing import List, Dict
from .operations import Operation

class RenamePlan:
    """存储重命名计划：原文件名 -> 新文件名"""
    def __init__(self, pairs: Dict[str, str]):
        self.pairs = pairs

    def has_conflicts(self) -> bool:
        """检查新文件名是否有重复"""
        new_names = list(self.pairs.values())
        return len(new_names) != len(set(new_names))

    def conflicts(self) -> List[str]:
        """返回重复的新文件名列表"""
        from collections import Counter
        cnt = Counter(self.pairs.values())
        return [name for name, count in cnt.items() if count > 1]

    def execute(self, log_path: str = "rename_log.json") -> None:
        """执行重命名，并将映射写入日志（用于撤销）"""
        if self.has_conflicts():
            raise ValueError("存在重命名冲突，请先解决冲突")
        # 写入日志（原文件名 -> 新文件名）
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.pairs, f, ensure_ascii=False, indent=2)
        # 执行重命名
        for old_name, new_name in self.pairs.items():
            os.rename(old_name, new_name)

def generate_plan(files: List[str], operations: List[Operation]) -> RenamePlan:
    """根据文件列表和操作列表生成重命名计划"""
    pairs = {}
    for f in files:
        new_name = f
        for op in operations:
            new_name = op.apply(new_name)
        pairs[f] = new_name
    return RenamePlan(pairs)

def undo_rename(log_path: str = "rename_log.json") -> None:
    """根据日志撤销上次重命名"""
    if not os.path.exists(log_path):
        raise FileNotFoundError("找不到日志文件，无法撤销")
    with open(log_path, "r", encoding="utf-8") as f:
        pairs = json.load(f)
    for old_name, new_name in pairs.items():
        if os.path.exists(new_name):
            os.rename(new_name, old_name)
            print(f"恢复: {new_name} -> {old_name}")
    os.remove(log_path)
    print("撤销完成。")