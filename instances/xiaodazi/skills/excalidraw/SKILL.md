---
name: excalidraw
description: Generate hand-drawn style diagrams, flowcharts, mind maps, and architecture diagrams in Excalidraw JSON format.
metadata:
  xiaodazi:
    dependency_level: external
    os: [common]
    backend_type: local
    user_facing: true
    external_tools:
      - excalidraw
    setup:
      user_hint: "需要 Excalidraw 来查看手绘图表，直接用网页版最方便"
      download_url: "https://github.com/excalidraw/excalidraw-desktop/releases"
      web_alternative: "https://excalidraw.com"
---

# 手绘风格图表（Excalidraw）

生成手绘风格的图表、流程图、思维导图、架构图，输出 Excalidraw JSON 格式文件。

## 使用场景

- 用户说「画个手绘风格的流程图」「帮我画个思维导图」
- 用户需要轻松亲切的图表风格（非正式场合）
- 用户想快速可视化想法，不需要太正式

## 执行方式

生成 Excalidraw JSON 格式文件（`.excalidraw`），用户可直接用 Excalidraw 打开编辑。

### 与 draw-io 的区别

| 特点 | Excalidraw | draw-io |
|---|---|---|
| 风格 | 手绘、轻松、亲切 | 专业、正式、规范 |
| 适用场景 | 头脑风暴、教学、非正式演示 | 正式文档、技术规范 |
| 编辑方式 | 网页/桌面 APP | 网页/桌面 APP |

### 支持的图表类型

1. **思维导图**：主题发散、知识梳理
2. **流程图**：简单流程、决策树
3. **概念图**：概念关系、知识网络
4. **架构图**：系统组件关系
5. **线框图**：简单 UI 草图

### JSON 生成规范

```json
{
  "type": "excalidraw",
  "version": 2,
  "elements": [
    {
      "type": "rectangle",
      "x": 100,
      "y": 100,
      "width": 200,
      "height": 80,
      "strokeColor": "#1e1e1e",
      "backgroundColor": "#a5d8ff",
      "fillStyle": "hachure",
      "roughness": 1,
      "roundness": { "type": 3 }
    }
  ]
}
```

### 配色方案

使用 Excalidraw 预设的柔和配色：

- 蓝色系：`#a5d8ff`（主节点）
- 绿色系：`#b2f2bb`（正面/完成）
- 黄色系：`#ffec99`（注意/进行中）
- 红色系：`#ffc9c9`（问题/阻塞）
- 紫色系：`#d0bfff`（辅助信息）

### 输出流程

1. 理解用户需求，确认图表类型
2. 生成 Excalidraw JSON 文件并保存
3. 告诉用户文件路径和打开方式

```bash
# 在线打开
# https://excalidraw.com/ → 导入文件

# 如果安装了桌面版
open /path/to/diagram.excalidraw
```

## 输出规范

- 生成的文件扩展名为 `.excalidraw`
- 默认使用手绘风格（roughness: 1）
- 节点间距合理，避免拥挤
- 文字使用 Excalidraw 内置的手写体
- 复杂图表先确认结构，再生成
