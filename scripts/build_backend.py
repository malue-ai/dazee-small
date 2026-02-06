"""
PyInstaller 后端构建脚本

将 Python FastAPI 后端打包为单文件可执行程序，
输出到 frontend/src-tauri/binaries/ 目录，
按 Tauri sidecar 命名约定命名。

用法:
    python scripts/build_backend.py              # 当前平台
    python scripts/build_backend.py --clean      # 清理后重新构建
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BINARIES_DIR = PROJECT_ROOT / "frontend" / "src-tauri" / "binaries"
SPEC_FILE = PROJECT_ROOT / "zenflux-backend.spec"


def get_target_triple() -> str:
    """
    获取当前平台的 Tauri target triple

    Tauri 要求 sidecar 二进制文件名包含平台标识：
    - macOS ARM:   aarch64-apple-darwin
    - macOS Intel: x86_64-apple-darwin
    - Windows:     x86_64-pc-windows-msvc
    - Linux:       x86_64-unknown-linux-gnu
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        arch = "aarch64" if machine == "arm64" else "x86_64"
        return f"{arch}-apple-darwin"
    elif system == "windows":
        return "x86_64-pc-windows-msvc"
    elif system == "linux":
        arch = "aarch64" if machine == "aarch64" else "x86_64"
        return f"{arch}-unknown-linux-gnu"
    else:
        raise RuntimeError(f"不支持的平台: {system} {machine}")


def get_binary_name() -> str:
    """获取带平台后缀的二进制文件名"""
    triple = get_target_triple()
    ext = ".exe" if platform.system().lower() == "windows" else ""
    return f"zenflux-backend-{triple}{ext}"


def clean_build() -> None:
    """清理构建产物"""
    dirs_to_clean = [
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "dist",
    ]
    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)
            print(f"已清理: {d}")


def build() -> Path:
    """
    执行 PyInstaller 构建

    Returns:
        构建产物路径
    """
    if not SPEC_FILE.exists():
        print(f"错误: spec 文件不存在: {SPEC_FILE}")
        sys.exit(1)

    print(f"平台: {get_target_triple()}")
    print(f"Spec: {SPEC_FILE}")
    print(f"输出: {BINARIES_DIR}")
    print()

    # 执行 PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
        "--clean",
        f"--distpath={PROJECT_ROOT / 'dist'}",
        f"--workpath={PROJECT_ROOT / 'build'}",
    ]

    print(f"执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print("构建失败")
        sys.exit(1)

    # PyInstaller --onefile 模式产物路径
    source = PROJECT_ROOT / "dist" / "zenflux-backend"
    if platform.system().lower() == "windows":
        source = source.with_suffix(".exe")

    if not source.exists():
        print(f"错误: 构建产物不存在: {source}")
        sys.exit(1)

    # 复制到 Tauri binaries 目录
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)
    target = BINARIES_DIR / get_binary_name()
    shutil.copy2(source, target)

    # macOS/Linux 设置可执行权限
    if platform.system().lower() != "windows":
        target.chmod(0o755)

    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"\n构建完成: {target}")
    print(f"文件大小: {size_mb:.1f} MB")

    return target


def main():
    parser = argparse.ArgumentParser(description="构建 Python 后端为可执行文件")
    parser.add_argument("--clean", action="store_true", help="清理后重新构建")
    args = parser.parse_args()

    print("=" * 60)
    print("ZenFlux Backend Builder")
    print("=" * 60)

    if args.clean:
        clean_build()

    build()


if __name__ == "__main__":
    main()
