"""命令行入口：批量重命名工具。

示例：
    python -m batch_renamer.cli ~/Pictures --prefix IMG_
    python -m batch_renamer.cli ~/Downloads --replace old new --dry-run
    python -m batch_renamer.cli ~/Downloads --index --index-digits 3 --index-start 1
    python -m batch_renamer.cli ~/Downloads --undo --log ~/Downloads/rename_log.json
"""

import argparse
import os
import sys

from .core import generate_plan, undo_rename
from .operations import AddPrefix, AddSuffix, ReplaceText, InsertIndex


def build_parser():
    parser = argparse.ArgumentParser(
        description="批量重命名工具 - 支持前缀、后缀、替换、插入序号，可预览和撤销"
    )
    parser.add_argument("directory", nargs="?", help="要处理的目录路径")
    parser.add_argument("--prefix", help="添加前缀")
    parser.add_argument("--suffix", help="添加后缀")
    parser.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"), help="替换文本")
    parser.add_argument("--index", action="store_true", help="插入序号")
    parser.add_argument("--index-start", type=int, default=1, help="序号起始值（默认 1）")
    parser.add_argument("--index-step", type=int, default=1, help="序号步长（默认 1）")
    parser.add_argument("--index-digits", type=int, default=0, help="序号最小位数，0 表示不补零（默认 0）")
    parser.add_argument("--index-position", choices=["start", "end"], default="end",
                        help="序号插入位置：start=文件名开头，end=扩展名前（默认 end）")
    parser.add_argument("--index-separator", default="_", help="序号与文件名之间的分隔符（默认 _）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不实际重命名")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过确认，直接执行")
    parser.add_argument("--undo", action="store_true", help="根据日志撤销上次操作")
    parser.add_argument("--log", default=None,
                        help="撤销日志路径（默认放在目标目录下的 rename_log.json）")
    return parser


def resolve_log_path(args):
    """日志默认放在目标目录，避免多个目录互相覆盖。"""
    if args.log:
        return args.log
    if args.directory:
        return os.path.join(os.path.abspath(args.directory), "rename_log.json")
    return "rename_log.json"


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # ---------- 撤销模式 ----------
    if args.undo:
        try:
            undo_rename(resolve_log_path(args))
            print("撤销完成。")
        except FileNotFoundError:
            print(f"没有找到撤销日志：{resolve_log_path(args)}")
        except Exception as e:
            print(f"撤销失败：{e}")
        return 0

    if not args.directory:
        parser.error("未指定目录（--undo 模式除外）")

    # ---------- 校验目录 ----------
    base_dir = os.path.abspath(args.directory)
    if not os.path.isdir(base_dir):
        print(f"错误：目录 {args.directory} 不存在", file=sys.stderr)
        return 1

    files = [
        f for f in sorted(os.listdir(base_dir))
        if not f.startswith(".") and os.path.isfile(os.path.join(base_dir, f))
    ]
    if not files:
        print("目录中没有文件")
        return 0

    # ---------- 构建操作 ----------
    operations = []
    if args.prefix:
        operations.append(AddPrefix(args.prefix))
    if args.suffix:
        operations.append(AddSuffix(args.suffix))
    if args.replace:
        operations.append(ReplaceText(args.replace[0], args.replace[1]))
    if args.index:
        operations.append(InsertIndex(
            start=args.index_start,
            step=args.index_step,
            digits=args.index_digits,
            position=args.index_position,
            separator=args.index_separator,
        ))

    if not operations:
        print("错误：请至少指定一个操作（--prefix, --suffix, --replace, --index）",
              file=sys.stderr)
        return 1

    # ---------- 生成计划（传 base_dir，产出绝对路径，无需 chdir） ----------
    plan = generate_plan(files, operations, base_dir=base_dir)

    changed = [(os.path.basename(o), os.path.basename(n)) for o, n in plan.pairs.items()]
    if all(o == n for o, n in changed):
        print("没有文件需要重命名")
        return 0

    print("重命名计划：")
    for old, new in changed:
        if old != new:
            print(f"  {old}  ->  {new}")

    # ---------- 冲突检测 ----------
    if plan.has_conflicts():
        print("\n警告：存在重命名冲突！")
        for name in plan.conflicts():
            print(f"  冲突：{name}")
        print("请调整参数后重试（预览模式下不会修改任何文件）。")
        return 1

    if args.dry_run:
        print("\n这是预览模式，不会实际修改文件。")
        return 0

    if not args.yes:
        try:
            confirm = input("\n确认执行重命名？(y/N): ")
        except EOFError:
            confirm = ""
        if confirm.strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 0

    try:
        plan.execute(log_path=resolve_log_path(args))
        print("重命名完成！")
        print(f"撤销日志：{resolve_log_path(args)}")
        return 0
    except Exception as e:
        print(f"执行失败：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
