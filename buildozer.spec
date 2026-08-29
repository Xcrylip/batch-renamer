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
requirements = python3==3.11.16,kivy==2.1.0

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