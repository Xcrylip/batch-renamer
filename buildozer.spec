[app]

# 应用名称（显示在手机桌面）
title = Batch Renamer

# 包名（应用的唯一标识，格式必须为反向域名，至少两段）
package.name = batchrenamer

# 包域名（通常与包名对应）
# 注意：不要用 org.example —— 这是 Android 官方示例域名，
#       被多数国产 ROM（MIUI/ColorOS/EMUI 等）和安全软件默认拉黑，
#       会导致 APK「安装被取消 / 被拦截」。
package.domain = com.xcrylip

# 源代码目录（包含 main.py 的目录，通常是项目根目录）
source.dir = .

# 需要包含的源代码文件或目录（多个用逗号分隔，默认包含所有）
# 注意：必须包含 ttf/ttc，否则 fonts/ 下的中文字体不会被打进 APK，
#       应用启动后找不到字体，界面上的中文会显示成 ☒（豆腐块）。
source.include_exts = py,png,jpg,kv,atlas,ttf,ttc,otf

# 排除的文件或目录
source.exclude_dirs = tests, bin

# 主入口文件（Kivy 应用的主文件）
# 说明：buildozer 会自动使用 source.dir 下的 main.py，无需额外声明；
#       此前误写为 `main.py = main.py`（不是合法的 buildozer 配置键，
#       会被静默忽略），这里删除以免误导。

# 版本号（显示给用户的版本名，例如「0.1」）
# 0.1.1: 修复横屏问题（buildozer.spec 补 orientation=portrait）
version = 0.1.1

# Android 内部版本号（必须是整数，且每次发新版必须增大）。
# 显式指定，避免依赖 buildozer 自动推导：
#   自动推导会生成类似 1021 这种带构建尾号的数字，版本不可控；
#   而当版本号不递增时，Android 会拒绝安装（提示「应用未安装 / 版本降级」）。
# 规则：主版本*10000 + 次版本*100 + 修订号，例如 0.1.0 -> 100。
# 100 -> 101: 横屏修复版，保证能覆盖安装旧包，无需卸载。
android.numeric_version = 101

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
# Android 11+ 说明：
#   READ/WRITE_EXTERNAL_STORAGE 在 API>=30 上基本失效（Scoped Storage）。
#   MANAGE_EXTERNAL_STORAGE 允许「所有文件访问」，是文件管理类 App 的正确做法。
#   运行时还需要引导用户到系统设置里手动授予「所有文件访问权限」。
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE

# Android API 级别
#   API 34 是 Android 14；用较新的目标 API 可避免「专为旧版 Android 打造」拦截。
android.api = 34

# 最低 Android API 级别
android.minapi = 21

# 自动接受 SDK 许可
android.accept_sdk_license = True

# 是否使用 AndroidX（通常启用）
android.androidx = True

# 应用图标（可选，不设置会使用默认）
# icon.filename = %(source.dir)s/icon.png

# ============================================================
# 屏幕方向（关键）
# ============================================================
# 取值：portrait=竖屏 / landscape=横屏 / all=跟随重力感应 / sensor=传感器
#
# ⚠️ 为什么必须显式写：python-for-android 对 screenOrientation 的
#    默认值是 landscape（横屏，历史原因——它早期主要面向游戏场景）。
#    不写这一行，AndroidManifest.xml 里就会生成
#    android:screenOrientation="landscape"，于是竖着拿手机界面也是横的。
#
# 本工具是文件列表类 UI，竖屏更符合使用习惯，故锁定 portrait。
orientation = portrait

# ============================================================
# 全屏
# ============================================================
# 0 = 显示状态栏（推荐，用户可以随时看到电量/时间）
# 1 = 隐藏状态栏（沉浸式，多见于游戏）
fullscreen = 0

# 日志级别
log_level = 2