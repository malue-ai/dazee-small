---
name: excel-analyzer
description: Analyze and process Excel/CSV files using pandas and openpyxl. Supports data summary, filtering, pivot tables, and chart generation.
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

## 输出规范

- 先展示数据概览（行数、列数、列名）
- 分析结果用表格格式展示
- 大数据集只展示前 10 行 + 汇总统计
- 导出文件时告知用户保存路径
