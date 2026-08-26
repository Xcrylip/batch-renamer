import os
import pytest
from batch_renamer.core import generate_plan, RenamePlan
from batch_renamer.operations import AddPrefix, AddSuffix, ReplaceText, InsertIndex

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

def test_conflict_detection():
    plan = RenamePlan({"a.txt": "same.txt", "b.txt": "same.txt"})
    assert plan.has_conflicts() == True
    assert plan.conflicts() == ["same.txt"]