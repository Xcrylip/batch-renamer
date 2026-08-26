import argparse
import os
from .core import generate_plan, undo_rename
from .operations import AddPrefix, AddSuffix, ReplaceText, InsertIndex

def main():
    parser = argparse.ArgumentParser(
        description="批量重命名工具 - 支持前缀、后缀、替换、插入序号，可预览和撤销"
    )
    parser.add_argument("directory", help="要处理的目录路径")
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
    parser.add_argument("--undo", action="store_true", help="根据日志撤销上次操作")
    parser.add_argument("--log", default="rename_log.json", help="撤销日志文件路径（默认 rename_log.json）")
    args = parser.parse_args()

    # 撤销模式
    if args.undo:
        try:
            undo_rename(args.log)
        except FileNotFoundError as e:
            print(e)
        return

    # 检查目录是否存在
    if not os.path.isdir(args.directory):
        print(f"错误：目录 {args.directory} 不存在")
        return

    # 获取目录下所有文件（不递归，如需递归可修改 os.walk）
    files = [f for f in os.listdir(args.directory) if os.path.isfile(os.path.join(args.directory, f))]
    if not files:
        print("目录中没有文件")
        return

    # 切换到目标目录，使文件名保持相对路径
    original_dir = os.getcwd()
    os.chdir(args.directory)

    # 构建操作列表
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
            separator=args.index_separator
        ))

    if not operations:
        print("错误：请至少指定一个操作（--prefix, --suffix, --replace, --index）")
        os.chdir(original_dir)
        return

    # 生成计划
    plan = generate_plan(files, operations)

    # 显示预览
    print("重命名计划：")
    for old, new in plan.pairs.items():
        print(f"  {old}  ->  {new}")

    # 冲突检测
    if plan.has_conflicts():
        print("\n警告：存在重命名冲突！")
        for name in plan.conflicts():
            print(f"  重复的新文件名: {name}")
        if not args.dry_run:
            print("请使用 --dry-run 预览并解决冲突后再执行。")
            os.chdir(original_dir)
            return
        else:
            print("\n这是预览模式，不会实际修改文件。")
    else:
        if args.dry_run:
            print("\n这是预览模式，不会实际修改文件。")
        else:
            confirm = input("\n确认执行重命名？(y/N): ")
            if confirm.lower() == 'y':
                try:
                    plan.execute(args.log)
                    print("重命名完成！")
                except Exception as e:
                    print(f"执行失败：{e}")
            else:
                print("已取消。")

    os.chdir(original_dir)

if __name__ == "__main__":
    main()