---
name: run-tests
description: 按本仓库约定运行 pytest、启动 uvicorn、定位测试失败并给出可复制命令。用于用户要求“跑测试/启动服务/复现问题/验证修复”或出现测试失败需要排查时。
---

# run-tests

## 适用场景（触发词）

- 跑测试：`pytest`、单测、集成测试、回归
- 启动服务：`uvicorn`、本地开发、热重载
- 需要把“怎么跑/跑哪一部分/失败怎么定位”写成可复制命令

## 强约束（必须遵守）

- **优先使用仓库指定虚拟环境**：仓库规则中给出了固定 venv 路径；如果本机不存在该路径，允许回退到当前已激活的 venv（并在输出里说明）
- **最小验证**：只跑与改动相关的测试/启动路径，避免无意义全量
- **不泄露敏感信息**：不要在命令或日志里输出 token/key；不要提交 `config.yaml`

## 快速命令（推荐直接复制）

### 跑测试（推荐）

```bash
# 所有测试
bash .cursor/skills/run-tests/scripts/pytest.sh

# 快速回归（示例）
bash .cursor/skills/run-tests/scripts/pytest.sh -q

# 跑某个文件
bash .cursor/skills/run-tests/scripts/pytest.sh tests/test_xxx.py -v
```

### 启动 API（推荐）

```bash
bash .cursor/skills/run-tests/scripts/uvicorn.sh
```

## 排障工作流（测试失败时）

1) **缩小范围**
- 先复现：只跑失败文件/失败用例（`pytest path::TestClass::test_case -vv`）

2) **区分类型**
- 用例断言失败 vs 依赖/环境缺失 vs 异步/并发问题 vs 时间/随机性问题

3) **收集关键证据**
- 失败堆栈（完整）
- 相关日志（注意不要包含敏感信息）
- 复现命令（可复制）

4) **修复后回归**
- 只跑相关测试 → 再跑最小冒烟（如启动 uvicorn 并命中关键接口/页面路径）

## 输出要求（交付物清单）

每次使用本 Skill，最终输出必须包含：

- **执行的命令**（可复制）
- **结果摘要**：通过/失败（失败要给出最短复现命令）
- **下一步**：若失败，列出 1-3 个最可能原因与验证方式

