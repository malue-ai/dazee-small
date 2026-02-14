"""
PyInstaller 后端构建脚本（onedir 模式）

将 Python FastAPI 后端打包为目录结构，
并将产物复制到 frontend/src-tauri/binaries/ 目录：
  - 主可执行文件 → binaries/xiaodazi-backend-{target-triple}
  - 依赖目录    → binaries/_internal/

Tauri 构建后需要 build_app.sh 将 _internal/ 复制到
.app/Contents/MacOS/_internal/ 并签名。

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
SPEC_FILE = PROJECT_ROOT / "xiaodazi-backend.spec"


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
    return f"xiaodazi-backend-{triple}{ext}"


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
    执行 PyInstaller 构建（onedir 模式）

    产物:
        dist/xiaodazi-backend/
          xiaodazi-backend       # 主可执行文件
          _internal/             # 所有依赖

    复制到:
        frontend/src-tauri/binaries/
          xiaodazi-backend-{target-triple}   # sidecar 主程序
          _internal/                        # 依赖目录（build_app.sh 后续处理）

    Returns:
        sidecar 主程序路径
    """
    if not SPEC_FILE.exists():
        print(f"错误: spec 文件不存在: {SPEC_FILE}")
        sys.exit(1)

    print(f"平台: {get_target_triple()}")
    print(f"Spec: {SPEC_FILE}")
    print(f"输出: {BINARIES_DIR}")
    print(f"模式: onedir（目录模式）")
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

    # onedir 模式产物：目录 dist/xiaodazi-backend/
    dist_dir = PROJECT_ROOT / "dist" / "xiaodazi-backend"
    if not dist_dir.is_dir():
        print(f"错误: 构建产物目录不存在: {dist_dir}")
        sys.exit(1)

    # 找到主可执行文件
    exe_name = "xiaodazi-backend"
    if platform.system().lower() == "windows":
        exe_name += ".exe"
    source_exe = dist_dir / exe_name

    if not source_exe.exists():
        print(f"错误: 主可执行文件不存在: {source_exe}")
        sys.exit(1)

    # ==================== 复制到 Tauri binaries 目录 ====================

    BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 复制主可执行文件（Tauri sidecar）
    target_exe = BINARIES_DIR / get_binary_name()
    shutil.copy2(source_exe, target_exe)
    if platform.system().lower() != "windows":
        target_exe.chmod(0o755)

    exe_size_mb = target_exe.stat().st_size / (1024 * 1024)
    print(f"\nsidecar 主程序: {target_exe} ({exe_size_mb:.1f} MB)")

    # 2. 复制 _internal/ 依赖目录
    #    PyInstaller 6.x 使用 _internal/ 子目录
    #    PyInstaller 5.x 将文件平铺在主程序旁边
    target_internal = BINARIES_DIR / "_internal"
    source_internal = dist_dir / "_internal"

    if source_internal.is_dir():
        # PyInstaller 6.x: 使用 _internal/ 目录
        if target_internal.exists():
            shutil.rmtree(target_internal)
        shutil.copytree(source_internal, target_internal)
        internal_size = sum(
            f.stat().st_size for f in target_internal.rglob("*") if f.is_file()
        )
        internal_size_mb = internal_size / (1024 * 1024)
        file_count = sum(1 for _ in target_internal.rglob("*") if _.is_file())
        print(f"依赖目录: {target_internal} ({internal_size_mb:.1f} MB, {file_count} 文件)")
    else:
        # PyInstaller 5.x: 文件平铺，复制除主程序外的所有文件/目录
        if target_internal.exists():
            shutil.rmtree(target_internal)
        target_internal.mkdir()
        copied = 0
        for item in dist_dir.iterdir():
            if item.name == exe_name:
                continue
            dest = target_internal / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
            copied += 1
        print(f"依赖目录: {target_internal} ({copied} 项，已从平铺结构收集)")

    # 3. 计算总大小
    total_size = target_exe.stat().st_size + sum(
        f.stat().st_size
        for f in target_internal.rglob("*")
        if f.is_file()
    )
    total_size_mb = total_size / (1024 * 1024)
    print(f"\n总大小: {total_size_mb:.1f} MB")
    print("构建完成")

    return target_exe


def main():
    parser = argparse.ArgumentParser(description="构建 Python 后端为可执行文件")
    parser.add_argument("--clean", action="store_true", help="清理后重新构建")
    args = parser.parse_args()

    print("=" * 60)
    print("xiaodazi Backend Builder (onedir)")
    print("=" * 60)

    if args.clean:
        clean_build()

    build()


if __name__ == "__main__":
    main()
