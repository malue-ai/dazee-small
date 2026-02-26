---
name: chart-image
description: Generate publication-quality chart images from data using matplotlib. Supports bar, line, pie, scatter, and more.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["matplotlib"]
---

# 数据图表生成

从数据生成高质量图表图片，支持柱状图、折线图、饼图、散点图等常见类型。

## 使用场景

- 用户说「把这些数据做成图表」「画一个柱状图」
- 用户提供了 Excel/CSV 数据，需要可视化
- 与 excel-analyzer 配合，分析后自动生成图表
- 用户说「做一个销售趋势图」「画个饼图看看占比」

## 执行方式

### 基本用法

```python
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 中文字体支持
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(10, 6))

# 示例：柱状图
categories = ['一月', '二月', '三月', '四月']
values = [120, 150, 180, 200]
ax.bar(categories, values, color='#4A90D9')

ax.set_title('月度销售额', fontsize=16, fontweight='bold')
ax.set_ylabel('金额（万元）')

plt.tight_layout()
plt.savefig('/tmp/chart.png', dpi=150, bbox_inches='tight')
plt.close()
```

### 支持的图表类型

| 类型 | 方法 | 适用场景 |
|---|---|---|
| 柱状图 | `ax.bar()` | 分类对比 |
| 折线图 | `ax.plot()` | 趋势变化 |
| 饼图 | `ax.pie()` | 占比分析 |
| 散点图 | `ax.scatter()` | 相关性分析 |
| 水平柱状图 | `ax.barh()` | 排名对比 |
| 堆叠图 | `ax.bar(bottom=)` | 组成分析 |

### 样式规范

- 默认配色：`#4A90D9`（蓝）、`#E85D75`（红）、`#50C878`（绿）、`#F5A623`（橙）
- 分辨率：150 DPI（屏幕查看）或 300 DPI（打印）
- 中文标题和标签必须设置中文字体
- 图例放在不遮挡数据的位置

## 输出规范

- 图表保存为 PNG 文件到临时目录
- 返回文件路径供用户查看或嵌入报告
- 自动选择最合适的图表类型（用户未指定时）
- 数据量大时自动截断或聚合，避免图表拥挤
