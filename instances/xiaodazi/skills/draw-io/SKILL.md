---
name: draw-io
description: Generate professional diagrams in draw.io XML format including flowcharts, org charts, UML diagrams, and network topology diagrams.
metadata:
  xiaodazi:
    dependency_level: external
    os: [common]
    backend_type: local
    user_facing: true
    external_tools:
      - draw.io
    setup:
      user_hint: "需要安装免费的 draw.io 画图工具，也可以直接用网页版"
      download_url: "https://github.com/jgraph/drawio-desktop/releases"
      web_alternative: "https://app.diagrams.net"
---

# 专业图表生成（draw.io）

生成专业级流程图、组织架构图、UML 图、网络拓扑图，输出 draw.io 兼容的 XML 文件。

## 使用场景

- 用户说「帮我画一个流程图」「画个组织架构图」「画个系统架构图」
- 用户需要正式文档中的专业图表
- 用户想可视化某个流程或结构

## 执行方式

生成 draw.io XML 格式文件，用户可直接用 draw.io（桌面版或在线版）打开编辑。

### 支持的图表类型

1. **流程图**：业务流程、审批流程、开发流程
2. **组织架构图**：公司/团队层级结构
3. **UML 图**：类图、序列图、用例图
4. **思维导图**：主题发散、知识结构
5. **网络拓扑图**：系统架构、网络结构
6. **甘特图/时间线**：项目排期

### XML 生成规范

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mxfile>
  <diagram name="Page-1">
    <mxGraphModel>
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- 节点和连线 -->
        <mxCell id="2" value="开始" style="rounded=1;whiteSpace=wrap;"
                vertex="1" parent="1">
          <mxGeometry x="100" y="100" width="120" height="60" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

### 样式规范

- 使用清晰的配色方案（蓝色系为主，红色标注重要节点）
- 节点间距均匀，布局整齐
- 连线使用直角折线或曲线，避免交叉
- 文字大小适中，中文使用 14px

### 输出流程

1. 理解用户需求，确认图表类型和内容
2. 生成 draw.io XML 文件并保存
3. 告诉用户文件路径和打开方式

```bash
# 检测是否安装了 draw.io
# macOS
open -a "draw.io" /path/to/diagram.drawio

# 或使用在线版
# https://app.diagrams.net/
```

## 输出规范

- 生成的文件扩展名为 `.drawio`
- 如果检测到用户安装了 draw.io，自动打开文件
- 如果没安装，提示用户可以用在线版打开
- 复杂图表先确认结构大纲，再生成完整 XML
