"""
构建 E2B 前端模板

使用方法：
    python scripts/build_frontend_template.py [--dev]
    
参数：
    --dev: 构建开发版本（默认构建生产版本）
"""

import os
import sys
import argparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from e2b import Template, default_build_logger

from infra.sandbox.templates.frontend_template import (
    frontend_template,
    FRONTEND_TEMPLATE_ALIAS,
    FRONTEND_TEMPLATE_ALIAS_DEV,
)

# 加载环境变量
load_dotenv()


def build_template(is_dev: bool = False):
    """
    构建前端模板
    
    Args:
        is_dev: 是否为开发版本
    """
    alias = FRONTEND_TEMPLATE_ALIAS_DEV if is_dev else FRONTEND_TEMPLATE_ALIAS
    env_type = "开发" if is_dev else "生产"
    
    print(f"🚀 开始构建 E2B 前端模板（{env_type}版本）...")
    print(f"   模板别名: {alias}")
    print(f"   基础镜像: node:20")
    print()
    
    try:
        result = Template.build(
            frontend_template,
            alias=alias,
            cpu_count=2,
            memory_mb=2048,
            on_build_logs=default_build_logger(),
        )
        
        print()
        print("=" * 50)
        print(f"✅ 模板构建成功！")
        print(f"   模板 ID: {result.template_id if hasattr(result, 'template_id') else 'N/A'}")
        print(f"   别名: {alias}")
        print()
        print("使用方法：")
        print(f'   sandbox = await AsyncSandbox.create(template="{alias}")')
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ 模板构建失败: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="构建 E2B 前端模板")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="构建开发版本"
    )
    
    args = parser.parse_args()
    build_template(is_dev=args.dev)


if __name__ == "__main__":
    main()
