---
name: excel-fixer
description: Auto-detect and fix common Excel formatting issues like merged cells, inconsistent types, duplicate headers, and encoding problems.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["pandas", "openpyxl"]
    auto_install: true
---

# Excel 格式修复

自动检测并修复 Excel/CSV 常见格式问题。

## 使用场景

- 用户说「这个表格打开乱码了」「帮我修一下这个 Excel」
- Excel 分析前预处理（自动清洗）
- 从外部导入的数据格式不规范

## 常见问题与修复

### 1. 编码乱码

```python
import pandas as pd
import chardet

def fix_encoding(file_path):
    """检测并修复 CSV 编码"""
    with open(file_path, 'rb') as f:
        raw = f.read(10000)
        detected = chardet.detect(raw)
        encoding = detected['encoding']
    
    # 尝试用检测到的编码读取
    df = pd.read_csv(file_path, encoding=encoding)
    
    # 保存为 UTF-8
    output = file_path.replace('.csv', '_fixed.csv')
    df.to_csv(output, encoding='utf-8-sig', index=False)
    return output, encoding
```

### 2. 合并单元格拆分

```python
from openpyxl import load_workbook

def unmerge_cells(file_path):
    """拆分合并单元格，向下填充值"""
    wb = load_workbook(file_path)
    ws = wb.active
    
    # 记录合并区域
    merged_ranges = list(ws.merged_cells.ranges)
    
    for merged in merged_ranges:
        # 获取合并区域左上角的值
        top_left_value = ws.cell(merged.min_row, merged.min_col).value
        
        # 取消合并
        ws.unmerge_cells(str(merged))
        
        # 向下填充
        for row in range(merged.min_row, merged.max_row + 1):
            for col in range(merged.min_col, merged.max_col + 1):
                ws.cell(row, col, top_left_value)
    
    output = file_path.replace('.xlsx', '_unmerged.xlsx')
    wb.save(output)
    return output, len(merged_ranges)
```

### 3. 重复表头检测

```python
def fix_duplicate_headers(df):
    """检测并修复重复表头行"""
    # 检查前几行是否与列名重复
    header_like_rows = []
    for i, row in df.head(5).iterrows():
        match_count = sum(1 for v in row.values if str(v) in df.columns.tolist())
        if match_count > len(df.columns) * 0.5:
            header_like_rows.append(i)
    
    if header_like_rows:
        df = df.drop(header_like_rows).reset_index(drop=True)
    
    return df, len(header_like_rows)
```

### 4. 数据类型不一致

```python
def fix_column_types(df):
    """检测并修复列内数据类型不一致"""
    fixes = []
    for col in df.columns:
        # 尝试转为数字
        numeric = pd.to_numeric(df[col], errors='coerce')
        non_null_ratio = numeric.notna().sum() / len(df)
        
        if non_null_ratio > 0.8 and df[col].dtype == object:
            # 80% 以上是数字，可能是数字列混入了文本
            bad_rows = df[numeric.isna() & df[col].notna()]
            fixes.append(f"列 '{col}': {len(bad_rows)} 行非数字值")
    
    return fixes
```

### 5. 一键修复流程

```python
def auto_fix(file_path):
    """自动检测并修复所有常见问题"""
    report = []
    
    # 1. 读取文件
    if file_path.endswith('.csv'):
        # 编码修复
        ...
    else:
        # 合并单元格修复
        ...
    
    # 2. 读取为 DataFrame
    df = pd.read_excel(file_path) if file_path.endswith('.xlsx') else pd.read_csv(file_path)
    
    # 3. 重复表头
    df, dup_count = fix_duplicate_headers(df)
    if dup_count:
        report.append(f"移除 {dup_count} 行重复表头")
    
    # 4. 数据类型
    type_issues = fix_column_types(df)
    report.extend(type_issues)
    
    # 5. 空行空列
    before = len(df)
    df = df.dropna(how='all')
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    after = len(df)
    if before != after:
        report.append(f"移除 {before - after} 行空行")
    
    return df, report
```

## 输出规范

- 修复前先展示检测到的问题清单
- 重大修改（如删除行/列）需要 HITL 确认
- 修复后保存为新文件（不覆盖原文件）
- 展示修复报告：修了什么、修了多少
