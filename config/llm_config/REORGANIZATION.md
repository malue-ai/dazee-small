# LLM 配置文件重组说明

## 🔄 重组原因

为了避免 `config/` 目录混乱，将所有 LLM 配置相关文件集中到专门的子目录 `config/llm_config/`。

## 📁 文件结构对比

### 重组前（混乱）

```
config/
├── llm_config_loader.py          # ❌ 与其他配置文件混在一起
├── llm_profiles.yaml             # ❌ 文件名不够简洁
├── llm_profiles.example.yaml     # ❌ 文件名不够简洁
├── README_LLM_CONFIG.md          # ❌ 文件名不够简洁
├── mem0_config.py                # 其他配置
├── embedding_config.py           # 其他配置
└── ...                           # 其他配置
```

**问题**：
- LLM 配置文件与其他配置文件混杂
- 文件名冗长（llm_profiles、README_LLM_CONFIG）
- 不便于管理和查找

### 重组后（清晰）

```
config/
├── llm_config/                   # ✅ LLM 配置专用目录
│   ├── __init__.py              # 模块导出接口
│   ├── loader.py                # 配置加载器
│   ├── profiles.yaml            # 核心配置文件（简洁）
│   ├── profiles.example.yaml    # 配置示例（简洁）
│   ├── README.md                # 使用文档（简洁）
│   └── REORGANIZATION.md        # 本文档
├── mem0_config.py                # 其他配置
├── embedding_config.py           # 其他配置
└── ...                           # 其他配置
```

**优势**：
- ✅ **独立目录**：LLM 配置与其他配置分离
- ✅ **结构清晰**：相关文件集中在一起
- ✅ **命名简洁**：profiles.yaml 比 llm_profiles.yaml 更清晰
- ✅ **模块化**：可作为独立模块导入
- ✅ **易于扩展**：未来可添加更多 LLM 相关配置

## 🔀 导入路径变化

### 修改前

```python
from config.llm_config_loader import get_llm_profile, list_profiles
```

### 修改后

```python
from config.llm_config import get_llm_profile, list_profiles
```

**优势**：
- ✅ 更符合 Python 模块命名规范
- ✅ 导入路径更简洁
- ✅ 便于理解（从 llm_config 模块导入）

## 📝 文件映射

| 旧文件路径 | 新文件路径 | 说明 |
|-----------|-----------|------|
| `config/llm_config_loader.py` | `config/llm_config/loader.py` | 配置加载器 |
| `config/llm_profiles.yaml` | `config/llm_config/profiles.yaml` | 核心配置文件 |
| `config/llm_profiles.example.yaml` | `config/llm_config/profiles.example.yaml` | 配置示例 |
| `config/README_LLM_CONFIG.md` | `config/llm_config/README.md` | 使用文档 |
| - | `config/llm_config/__init__.py` | **新增**：模块接口 |
| - | `config/llm_config/REORGANIZATION.md` | **新增**：本说明文档 |

## ✅ 已完成工作

### 1. 文件移动
- ✅ 创建 `config/llm_config/` 子目录
- ✅ 复制所有配置文件到新目录
- ✅ 重命名文件（简化命名）
- ✅ 删除旧文件

### 2. 代码更新
- ✅ 更新 `loader.py` 中的文件路径
- ✅ 创建 `__init__.py` 模块接口
- ✅ 更新所有代码中的 import 路径（6 个文件）
  - `core/inference/semantic_inference.py`
  - `core/prompt/llm_analyzer.py`
  - `core/agent/factory.py`
  - `core/tool/instance_registry.py`
  - `utils/background_tasks.py`
  - `tools/plan_todo_tool.py`

### 3. 文档更新
- ✅ 更新 `README.md` 中的路径引用
- ✅ 更新 `LLM_CONFIG_MIGRATION.md` 中的说明
- ✅ 创建本重组说明文档

### 4. 质量检查
- ✅ 所有代码通过 Linter 检查
- ✅ 无 import 错误
- ✅ 文件结构清晰

## 🚀 使用方法

### 查看配置

```python
from config.llm_config import list_profiles

profiles = list_profiles()
for name, desc in profiles.items():
    print(f"{name}: {desc}")
```

### 获取配置

```python
from config.llm_config import get_llm_profile
from core.llm import create_llm_service

# 获取配置
profile = get_llm_profile("semantic_inference")

# 创建 LLM 服务
llm = create_llm_service(**profile)
```

### 修改配置

编辑 `config/llm_config/profiles.yaml`：

```yaml
profiles:
  semantic_inference:
    model: "claude-haiku-4-5-20251001"
    max_tokens: 1000  # 修改配置
    temperature: 0
```

### 重新加载配置

```python
from config.llm_config import reload_config

reload_config()  # 配置修改后热加载
```

## 📚 相关文档

- [README.md](README.md) - 完整使用文档
- [profiles.yaml](profiles.yaml) - 核心配置文件
- [profiles.example.yaml](profiles.example.yaml) - 配置示例
- [../LLM_CONFIG_MIGRATION.md](../LLM_CONFIG_MIGRATION.md) - 配置化迁移总结

## 🎯 最佳实践

1. **配置文件管理**
   - 只修改 `profiles.yaml`，不要修改 `profiles.example.yaml`
   - 使用 Git 版本控制管理配置变更
   - 重大调整前备份配置

2. **代码导入**
   - 始终使用 `from config.llm_config import ...` 导入
   - 不要直接导入 `loader.py` 中的函数
   - 使用模块提供的公共接口

3. **文件结构**
   - 不要在 `config/llm_config/` 外创建 LLM 配置文件
   - 新增 LLM Profile 直接在 `profiles.yaml` 中添加
   - 保持目录结构整洁

---

**重组日期**: 2025-01-09  
**影响范围**: 6 个代码文件的 import 路径  
**新增文件**: 2 个（`__init__.py`、`REORGANIZATION.md`）  
**删除文件**: 4 个（旧位置的文件）  
**代码质量**: 无 Linter 错误
