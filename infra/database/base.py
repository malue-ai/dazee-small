"""
SQLAlchemy 模型基类
"""

from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass
from sqlalchemy import MetaData

# 命名约定（用于自动生成约束名称）
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}


class Base(DeclarativeBase):
    """
    SQLAlchemy 声明式基类
    
    所有模型都应该继承此基类
    """
    metadata = MetaData(naming_convention=naming_convention)

