import os
import json
import tempfile
from typing import List, Dict, Optional
from .operations import Operation


class RenamePlan:
    """存储重命名计划：原路径 -> 新路径。

    路径一律使用「绝对路径」，避免依赖 os.chdir（Android 上 chdir 不可靠）。
    pairs 的 key/value 都是绝对路径。
    """

    def __init__(self, pairs: Dict[str, str], base_dir: Optional[str] = None):
        self.pairs = pairs
        self.base_dir = base_dir

    # ---------- 冲突检测 ----------

    def _effective(self) -> Dict[str, str]:
        """只保留真正发生变化的项（自己改给自己的忽略）。"""
        return {o: n for o, n in self.pairs.items() if o != n}

    def has_conflicts(self) -> bool:
        """检查新旧名是否有冲突或会造成覆盖。"""
        eff = self._effective()
        new_paths = list(eff.values())
        # 1) 多个文件改成同一个新名字
        if len(new_paths) != len(set(new_paths)):
            return True
        # 2) 新名字指向一个「不在本次计划里」的既有文件 -> 会覆盖
        old_paths = set(eff.keys())
        for new_path in new_paths:
            if new_path in old_paths:
                continue
            if os.path.exists(new_path):
                return True
        return False

    def conflicts(self) -> List[str]:
        """返回有问题的目标路径列表（重复 或 会覆盖既有文件）。"""
        from collections import Counter

        eff = self._effective()
        result: List[str] = []
        cnt = Counter(eff.values())
        for name, count in cnt.items():
            if count > 1:
                result.append(name)

        old_paths = set(eff.keys())
        for new_path in eff.values():
            if new_path in old_paths:
                continue
            if os.path.exists(new_path) and new_path not in result:
                result.append(new_path)
        return result

    # ---------- 执行 ----------

    def execute(self, log_path: str = "rename_log.json") -> None:
        """执行重命名（两步法，避免链式冲突），并写入撤销日志。

        为什么用两步法？
          假设计划是 a.txt -> b.txt 且 b.txt -> c.txt。
          若按顺序直接改：先 a.txt->b.txt，则 b.txt 已被 a 占用，
          再想把「原来的 b.txt」->c.txt 就找不到文件了。
          两步法先全部改成临时名，再改成最终名，彻底规避该问题。
        """
        if self.has_conflicts():
            raise ValueError("存在重命名冲突，请先解决冲突")

        eff = self._effective()
        if not eff:
            return

        # 先写日志：即使随后崩溃，也能撤销
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(eff, f, ensure_ascii=False, indent=2)

        tmp_map: Dict[str, str] = {}  # 临时路径 -> 最终路径
        origin_of: Dict[str, str] = {}  # 最终路径 -> 原始路径（回滚用）
        tmp_of: Dict[str, str] = {}  # 临时路径 -> 原始路径（回滚用）

        try:
            # 第一步：全部改成临时名
            for old_path in eff:
                d = os.path.dirname(old_path)
                fd, tmp_path = tempfile.mkstemp(prefix=".ren_tmp_", dir=d or None)
                os.close(fd)
                os.remove(tmp_path)  # 只要一个不冲突的名字
                os.rename(old_path, tmp_path)
                tmp_map[tmp_path] = eff[old_path]
                origin_of[eff[old_path]] = old_path
                tmp_of[tmp_path] = old_path

            # 第二步：临时名 -> 最终名
            done_tmp: List[str] = []
            for tmp_path, new_path in tmp_map.items():
                os.rename(tmp_path, new_path)
                done_tmp.append(tmp_path)

            # 成功：清理回滚信息
            tmp_of.clear()
            origin_of.clear()

        except Exception:
            # 回滚：把已经改过的文件恢复成「原始名字」
            # 注意：分两种状态 —— 还在临时名、以及已经变成最终名
            for tmp_path, new_path in tmp_map.items():
                try:
                    if os.path.exists(tmp_path):
                        # 仍处于临时名状态 -> 直接改回原名
                        os.rename(tmp_path, tmp_of[tmp_path])
                    elif os.path.exists(new_path) and new_path in origin_of:
                        # 已改成最终名 -> 改回原名
                        os.rename(new_path, origin_of[new_path])
                except OSError:
                    pass
            raise


def generate_plan(files: List[str], operations: List[Operation],
                  base_dir: Optional[str] = None) -> RenamePlan:
    """根据文件列表和操作列表生成重命名计划。

    :param files: 文件名列表（相对名）。
    :param operations: 操作列表。
    :param base_dir: 这些文件所在目录的绝对路径。传入后，
                     计划里的 key/value 都会是绝对路径，执行时无需 chdir。
    """
    # 关键：每次都重置带状态的算子（如 InsertIndex），保证预览与执行一致
    for op in operations:
        reset = getattr(op, "reset", None)
        if callable(reset):
            reset()

    pairs: Dict[str, str] = {}
    for f in files:
        new_name = f
        for op in operations:
            new_name = op.apply(new_name)

        if base_dir:
            pairs[os.path.join(base_dir, f)] = os.path.join(base_dir, new_name)
        else:
            pairs[f] = new_name
    return RenamePlan(pairs, base_dir=base_dir)


def undo_rename(log_path: str = "rename_log.json") -> None:
    """根据日志撤销上次重命名。

    同样使用两步法（先临时名再原名），避免 a->b、b->c 的逆操作互相覆盖。
    """
    if not os.path.exists(log_path):
        raise FileNotFoundError("找不到日志文件，无法撤销")

    with open(log_path, "r", encoding="utf-8") as f:
        pairs = json.load(f)

    # 日志记录 原路径 -> 新路径；撤销即 新路径 -> 原路径
    to_restore = {new: old for old, new in pairs.items() if new != old}
    existing = {new: old for new, old in to_restore.items() if os.path.exists(new)}

    if not existing:
        os.remove(log_path)
        return

    tmp_map: Dict[str, str] = {}
    try:
        for new_path in existing:
            d = os.path.dirname(new_path)
            fd, tmp_path = tempfile.mkstemp(prefix=".ren_undo_", dir=d or None)
            os.close(fd)
            os.remove(tmp_path)
            os.rename(new_path, tmp_path)
            tmp_map[tmp_path] = existing[new_path]

        for tmp_path, old_path in tmp_map.items():
            os.rename(tmp_path, old_path)
    except Exception:
        for tmp_path, old_path in tmp_map.items():
            if os.path.exists(tmp_path):
                try:
                    os.rename(tmp_path, old_path)
                except OSError:
                    pass
        raise

    os.remove(log_path)