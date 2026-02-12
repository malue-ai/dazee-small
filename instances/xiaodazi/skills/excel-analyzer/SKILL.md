---
name: excel-analyzer
description: Analyze and process Excel/CSV files using pandas and openpyxl. Supports data summary, filtering, pivot tables, and chart generation.
version: "1.0.0"
parameters:
  - name: file_path
    type: string
    required: true
    description: "Excel/CSV 文件路径"
  - name: task
    type: string
    enum: [summary, filter, pivot, chart, custom]
    default: summary
    description: "分析任务类型"
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages:
      - pandas
      - openpyxl
---

# Excel 分析

帮助用户分析和处理 Excel/CSV 文件。

## 使用场景

- 用户说「帮我分析这个表格」「这个 Excel 里有多少条数据」
- 用户需要对表格做筛选、汇总、透视
- 用户想从 Excel 生成图表或报告

## 依赖安装

首次使用时自动安装：

```bash
pip install pandas openpyxl
```

## 执行方式

通过 Python 脚本使用 pandas 处理 Excel/CSV 文件。

### 读取文件

```python
import pandas as pd

# 读取 Excel
df = pd.read_excel("/path/to/file.xlsx", sheet_name=0)

# 读取 CSV
df = pd.read_csv("/path/to/file.csv")

# 查看基本信息
print(f"行数: {len(df)}, 列数: {len(df.columns)}")
print(f"列名: {list(df.columns)}")
print(df.head())
```

### 数据汇总

```python
# 基本统计
print(df.describe())

# 按列汇总
print(df.groupby("类别").agg({"金额": ["sum", "mean", "count"]}))
```

### 数据筛选

```python
# 条件筛选
filtered = df[df["金额"] > 1000]

# 多条件
filtered = df[(df["部门"] == "销售") & (df["金额"] > 500)]
```

### 导出结果

```python
# 导出到新 Excel
result.to_excel("/path/to/output.xlsx", index=False)

# 导出到 CSV
result.to_csv("/path/to/output.csv", index=False, encoding="utf-8-sig")
```

## 数据校验（必须执行）

分析前和分析后都要做数据校验，确保结果可信：

### 清洗后校验

```python
# 1. 行数校验：打印清洗前后行数，确认只去了空行/噪音行
print(f"清洗前: {len(df_raw)} 行 → 清洗后: {len(df_clean)} 行 (去除 {len(df_raw)-len(df_clean)} 行)")

# 2. 分类列去重：检查分类列（如地区、产品）是否有近似重复值
for col in categorical_columns:
    unique_vals = df_clean[col].unique()
    print(f"列 '{col}' 唯一值: {unique_vals}")
    # 检查近似重复（如 "华东" vs "华东地区"）
    # 如有近似重复，合并为统一值

# 3. 聚合一致性校验：各分组 sum 必须等于总 sum
total = df_clean["金额"].sum()
group_total = df_clean.groupby("地区")["金额"].sum().sum()
assert abs(total - group_total) < 0.01, f"聚合不一致: 总额 {total} ≠ 分组合计 {group_total}"
```

### 报告校验

- 报告中引用的数字必须与清洗后数据一致
- 如有排名/占比，各项占比之和应约等于 100%
- 明确告知用户做了哪些清洗（统一了几种日期格式、去了多少空行等）

## 输出规范

- 先展示数据概览（行数、列数、列名）
- **明确告知清洗步骤**：做了什么修复、去了多少行、统一了什么格式
- 分析结果用表格格式展示
- 大数据集只展示前 10 行 + 汇总统计
- 导出文件时告知用户保存路径
