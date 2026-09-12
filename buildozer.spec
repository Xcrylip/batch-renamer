[app]

# 应用名称（显示在手机桌面）
title = Batch Renamer

# 包名（应用的唯一标识，格式必须为反向域名，至少两段）
package.name = batchrenamer

# 包域名（通常与包名对应，可以随便写，但建议用你自己的域名或 github.io）
package.domain = org.example

# 源代码目录（包含 main.py 的目录，通常是项目根目录）
source.dir = .

# 需要包含的源代码文件或目录（多个用逗号分隔，默认包含所有）
source.include_exts = py,png,jpg,kv,atlas

# 排除的文件或目录
source.exclude_dirs = tests, bin

# 主入口文件（Kivy 应用的主文件）
main.py = main.py

# 版本号
version = 0.1

# 依赖的 Python 模块（会自动通过 pip 安装）
# 不钉死版本：让 python-for-android 自动匹配 hostpython3，避免出现
# "python3 should have same version as hostpython3" 这类版本冲突
requirements = python3,kivy

# ============================================================
# 关键修复：把 python-for-android 钉到 v2024.01.21
# ============================================================
# 原因：
#   p4a 的 master/develop 分支（含最新的 v2026.05.09 tag）里，
#   hostpython3 与 python3 两个 recipe 的 Python 版本已被硬编码为
#   3.14.2（源码里写死 `version = "3.14.2"`，无法用环境变量覆盖）。
#
#   Python 3.14.2 太新，p4a 给这个 Python 建 venv 时 pip 自举会崩：
#     RAN: bash -c 'source venv/bin/activate && pip install -U pip'
#     ImportError: cannot import name 'BuildDependencyInstallError'
#                  from 'pip._internal.exceptions'
#   这是 p4a 自带 pip 与 Python 3.14 不兼容导致的上游 bug，与本项目无关。
#
#   v2024.01.21 是 p4a 最后一个使用 Python 3.11.x 的稳定 tag
#   （hostpython3 与 python3 recipe 版本均为 3.11.5，内部自洽），
#   且该版本不包含 fix_ensurepip.patch，走的是成熟稳定的
#   venv + ensurepip 流程，不会触发上述崩溃。
#
#   注意：不要改成 master / develop，否则 Python 版本又会回到 3.14。
p4a.branch = v2024.01.21

# 需要的权限（Android 权限）
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

# Android API 级别（建议 31 或更高）
android.api = 31

# 最低 Android API 级别
android.minapi = 21

# 自动接受 SDK 许可
android.accept_sdk_license = True

# 是否使用 AndroidX（通常启用）
android.androidx = True

# 应用图标（可选，不设置会使用默认）
# icon.filename = %(source.dir)s/icon.png

# 日志级别
log_level = 2