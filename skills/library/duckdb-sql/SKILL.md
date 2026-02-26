---
name: duckdb-sql
description: Analytical SQL engine for querying CSV, Parquet, and JSON files directly. No database setup required.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["duckdb"]
---

# DuckDB SQL 分析引擎

用 SQL 直接查询 CSV、Parquet、JSON 文件，无需导入数据库。适合大数据集分析。

## 使用场景

- 用户说「用 SQL 分析这个 CSV 文件」「这个数据集有多少行」
- 数据量大（>10万行），excel-analyzer 处理较慢时
- 用户需要复杂聚合、JOIN、窗口函数等 SQL 功能
- 用户说「对比这两个 CSV 文件的差异」

## 与 excel-analyzer 的区别

| 工具 | 擅长 | 局限 |
|---|---|---|
| excel-analyzer | 小数据集、图表、格式化输出 | 大数据集慢 |
| **duckdb-sql** | **大数据集、复杂 SQL、多文件 JOIN** | 不做格式化输出 |

## 执行方式

### Python API

```python
import duckdb

con = duckdb.connect()

# 直接查询 CSV
result = con.sql("SELECT * FROM 'data.csv' LIMIT 10").fetchdf()

# 聚合分析
result = con.sql("""
    SELECT category, COUNT(*) as count, AVG(price) as avg_price
    FROM 'sales.csv'
    GROUP BY category
    ORDER BY count DESC
""").fetchdf()

# 多文件 JOIN
result = con.sql("""
    SELECT o.order_id, c.name, o.total
    FROM 'orders.csv' o
    JOIN 'customers.csv' c ON o.customer_id = c.id
    WHERE o.total > 1000
""").fetchdf()

# 查询 Parquet
result = con.sql("SELECT * FROM 'data.parquet' WHERE year = 2026").fetchdf()

# 通配符查询多文件
result = con.sql("SELECT * FROM 'logs/*.csv'").fetchdf()
```

### 命令行用法

```bash
# 安装
pip install duckdb

# 交互式
python3 -c "import duckdb; print(duckdb.sql(\"SELECT count(*) FROM 'data.csv'\").fetchone())"
```

### 常用分析模式

```sql
-- 数据概览
SUMMARIZE SELECT * FROM 'data.csv';

-- 去重计数
SELECT COUNT(DISTINCT user_id) FROM 'events.csv';

-- 窗口函数：排名
SELECT *, RANK() OVER (PARTITION BY department ORDER BY salary DESC) as rank
FROM 'employees.csv';

-- 导出结果
COPY (SELECT * FROM 'data.csv' WHERE status = 'active') TO 'output.csv';
```

## 输出规范

- 查询结果以表格格式展示（前 20 行 + 总行数）
- 大结果集自动截断，提示用户添加 LIMIT
- 查询耗时超过 5 秒时显示进度提示
