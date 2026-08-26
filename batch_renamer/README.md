# Batch Renamer

一个简单、安全的 Python 命令行批量重命名工具。支持添加前缀/后缀、文本替换、插入序号，并提供预览和撤销功能。

## 功能

- 添加前缀：`--prefix "img_"`
- 添加后缀：`--suffix "backup"`（默认分隔符 `_`）
- 文本替换：`--replace "old" "new"`
- 插入序号：`--index`，可通过参数自定义起始值、步长、位数、位置和分隔符
- 预览模式：`--dry-run` 只显示重命名计划，不实际修改文件
- 撤销功能：使用 `--undo` 根据日志恢复原名

## 安装与使用

无需安装依赖，Python 3.6+ 即可运行。

```bash
# 预览：在目录 ./photos 中为所有文件添加前缀 "vacation_"
python -m batch_renamer.cli ./photos --prefix "vacation_" --dry-run

# 执行：确认无误后去掉 --dry-run 并输入 y
python -m batch_renamer.cli ./photos --prefix "vacation_"

# 撤销上次操作
python -m batch_renamer.cli ./photos --undo