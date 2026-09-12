"""核心逻辑单元测试。

注意：部分用例刻意不传 base_dir，走「相对路径」分支，
方便断言可读的短文件名；绝对路径行为单独用 test_absolute_paths 覆盖。
"""

import os
import pytest

from batch_renamer.core import generate_plan, RenamePlan, undo_rename
from batch_renamer.operations import AddPrefix, AddSuffix, ReplaceText, InsertIndex


# ---------------- 基础算子 ----------------

def test_add_prefix():
    plan = generate_plan(["a.txt", "b.txt"], [AddPrefix("pre_")])
    assert plan.pairs == {"a.txt": "pre_a.txt", "b.txt": "pre_b.txt"}


def test_add_suffix():
    plan = generate_plan(["file.txt"], [AddSuffix("backup")])
    assert plan.pairs == {"file.txt": "file_backup.txt"}


def test_replace():
    plan = generate_plan(["file1.txt"], [ReplaceText("1", "2")])
    assert plan.pairs == {"file1.txt": "file2.txt"}


def test_insert_index_end():
    op = InsertIndex(start=1, step=1, digits=2, position="end", separator="_")
    plan = generate_plan(["a.txt", "b.txt"], [op])
    assert plan.pairs == {"a.txt": "a_01.txt", "b.txt": "b_02.txt"}


def test_insert_index_start():
    op = InsertIndex(start=5, step=5, digits=0, position="start", separator="-")
    plan = generate_plan(["doc.txt", "img.txt"], [op])
    assert plan.pairs == {"doc.txt": "5-doc.txt", "img.txt": "10-img.txt"}


# ---------------- 序号重置（回归 bug：连点两次预览结果不一致） ----------------

def test_insert_index_reset_between_plans():
    op = InsertIndex(start=1, digits=2)
    plan1 = generate_plan(["a.txt", "b.txt"], [op])
    plan2 = generate_plan(["a.txt", "b.txt"], [op])
    assert plan1.pairs == plan2.pairs, "复用同一个算子对象时，第二次计划必须重新从 start 计数"


def test_insert_index_explicit_reset():
    op = InsertIndex(start=10, digits=2)
    op.apply("x.txt")
    op.reset()
    assert op.apply("x.txt") == "x_10.txt"


# ---------------- 冲突检测 ----------------

def test_conflict_detection():
    plan = RenamePlan({"a.txt": "same.txt", "b.txt": "same.txt"})
    assert plan.has_conflicts() is True
    assert plan.conflicts() == ["same.txt"]


def test_no_conflict_when_unchanged():
    plan = RenamePlan({"a.txt": "a.txt", "b.txt": "b.txt"})
    assert plan.has_conflicts() is False
    assert plan.conflicts() == []


def test_conflict_when_overwriting_existing_file(tmp_path):
    """目标文件名已被现有文件占用（且不在计划内）→ 应判为冲突。"""
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "taken.txt").write_text("existing")

    plan = generate_plan(["a.txt"], [ReplaceText("a", "taken")], base_dir=str(tmp_path))
    assert plan.has_conflicts() is True


# ---------------- 绝对路径模式 ----------------

def test_absolute_paths(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")

    plan = generate_plan(["a.txt", "b.txt"], [AddPrefix("pre_")], base_dir=str(tmp_path))
    expected = {
        str(tmp_path / "a.txt"): str(tmp_path / "pre_a.txt"),
        str(tmp_path / "b.txt"): str(tmp_path / "pre_b.txt"),
    }
    assert plan.pairs == expected


def test_execute_and_undo_roundtrip(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")

    log = str(tmp_path / "rename_log.json")
    plan = generate_plan(["a.txt", "b.txt"], [AddPrefix("pre_")], base_dir=str(tmp_path))
    plan.execute(log_path=log)

    assert (tmp_path / "pre_a.txt").exists()
    assert (tmp_path / "pre_b.txt").exists()
    assert not (tmp_path / "a.txt").exists()

    undo_rename(log)
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").exists()
    assert not (tmp_path / "pre_a.txt").exists()


def test_execute_chain_rename(tmp_path):
    """a.txt -> b.txt, b.txt -> c.txt 的链式改名不能互相覆盖。"""
    (tmp_path / "a.txt").write_text("A")
    (tmp_path / "b.txt").write_text("B")

    plan = RenamePlan(
        {
            str(tmp_path / "a.txt"): str(tmp_path / "b.txt"),
            str(tmp_path / "b.txt"): str(tmp_path / "c.txt"),
        }
    )
    plan.execute(log_path=str(tmp_path / "log.json"))

    assert (tmp_path / "b.txt").read_text() == "A"
    assert (tmp_path / "c.txt").read_text() == "B"
    assert not (tmp_path / "a.txt").exists()


def test_execute_rollback_on_failure(tmp_path, monkeypatch):
    """中途失败时必须回滚成「原始文件名」，不能留下半截状态。"""
    (tmp_path / "a.txt").write_text("A")
    (tmp_path / "b.txt").write_text("B")

    plan = generate_plan(["a.txt", "b.txt"], [AddPrefix("pre_")], base_dir=str(tmp_path))

    real_rename = os.rename
    calls = {"n": 0}

    def flaky_rename(src, dst):
        calls["n"] += 1
        # 第 3 次调用 = 第二步（最终改名阶段）的第一次 -> 那时已有 1 个文件变成了最终名
        if calls["n"] == 3:
            raise OSError("模拟磁盘错误")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", flaky_rename)

    with pytest.raises(Exception):
        plan.execute(log_path=str(tmp_path / "log.json"))

    # 回滚后必须恢复成原始文件名
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").exists()
    assert not (tmp_path / "pre_a.txt").exists()
    assert not (tmp_path / "pre_b.txt").exists()


# ---------------- 撤销 ----------------

def test_undo_without_log(tmp_path):
    with pytest.raises(FileNotFoundError):
        undo_rename(str(tmp_path / "nope.json"))