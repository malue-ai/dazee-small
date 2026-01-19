"""
部署环境配置管理

支持两种部署环境：
1. 本地测试环境（local/development）：使用本地 Redis，便于开发和验证
2. AWS 生产部署环境（aws/production）：使用 AWS MemoryDB，生产环境
"""

import os
from pathlib import Path
from typing import Literal

# 部署环境：从环境变量读取，默认为本地环境
# 可选值：local, development, aws, production
DEPLOYMENT_ENV = os.getenv("DEPLOYMENT_ENV", "local").lower()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _get_redis_config() -> tuple[str, str]:
    """根据部署环境返回 Redis 配置"""
    if DEPLOYMENT_ENV in ("local", "development"):
        # 本地测试环境：使用本地 Redis
        return (
            "redis://localhost:6379/0",
            "本地 Redis（本地测试环境）"
        )
    elif DEPLOYMENT_ENV in ("aws", "production"):
        # AWS 生产部署环境：使用 AWS MemoryDB
        return (
            "rediss://agentuser:y05EtW8goYEBOpMYB52lPh8qHnRZggcc@"
            "clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com:6379",
            "AWS MemoryDB（AWS 生产部署环境）"
        )
    else:
        # 默认使用本地环境
        return (
            "redis://localhost:6379/0",
            f"本地 Redis（未知环境: {DEPLOYMENT_ENV}，默认使用本地）"
        )


class DeploymentConfig:
    """部署环境配置类"""
    
    # PostgreSQL 配置（两种环境相同，都使用 AWS RDS）
    DATABASE_URL = (
        "postgresql+asyncpg://postgres:924Ff8O5kfEWOvzj3nN1ricrWVTIHSy8@"
        "zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com:5432/"
        "zen0_staging_pg"
    )
    
    # Redis 配置（根据部署环境选择）
    REDIS_URL, REDIS_DESCRIPTION = _get_redis_config()
    
    @classmethod
    def setup_env(cls):
        """设置环境变量"""
        os.environ["DATABASE_URL"] = cls.DATABASE_URL
        os.environ["REDIS_URL"] = cls.REDIS_URL
        
        print(f"\n{'='*60}")
        print(f"📋 部署环境配置")
        print(f"{'='*60}")
        print(f"部署环境: {DEPLOYMENT_ENV.upper()}")
        print(f"PostgreSQL: {cls.DATABASE_URL[:50]}...")
        print(f"Redis: {cls.REDIS_DESCRIPTION}")
        print(f"{'='*60}\n")
    
    @classmethod
    def is_local_env(cls) -> bool:
        """判断是否为本地测试环境"""
        return DEPLOYMENT_ENV in ("local", "development")
    
    @classmethod
    def is_aws_env(cls) -> bool:
        """判断是否为 AWS 生产部署环境"""
        return DEPLOYMENT_ENV in ("aws", "production")
    
    @classmethod
    def get_env_name(cls) -> str:
        """获取环境名称"""
        if cls.is_local_env():
            return "本地测试环境"
        elif cls.is_aws_env():
            return "AWS 生产部署环境"
        else:
            return f"未知环境 ({DEPLOYMENT_ENV})"


# 自动设置环境变量
DeploymentConfig.setup_env()

# 为了向后兼容，保留 TestConfig 别名
TestConfig = DeploymentConfig
