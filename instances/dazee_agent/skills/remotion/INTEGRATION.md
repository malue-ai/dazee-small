# Remotion Skill 集成指南

## 概述

本文档描述如何将 Remotion Skill 深度集成到 dazee_agent 实例，实现基于用户意图的自动发现和调用。

## 集成架构

```
用户请求
    │
    ▼
┌─────────────────────────────────────┐
│        意图识别 (Intent Analyzer)    │
│  intent_prompt.md 判断意图类型       │
└─────────────────────────────────────┘
    │
    │ 识别到视频/动画关键词
    ▼
┌─────────────────────────────────────┐
│        意图3: 综合咨询              │
│  routing: "Remotion Skill"          │
└─────────────────────────────────────┘
    │
    │ needs_plan: true/false
    ▼
┌─────────────────────────────────────┐
│        Plan 规划阶段                │
│  创建视频创作任务的执行计划          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│        Skill 加载                   │
│  加载 remotion/SKILL.md             │
│  根据需求选择规则文件               │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│        代码生成                     │
│  基于规则生成 Remotion React 代码    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│        结果输出                     │
│  完整代码 + 配置 + 运行指引          │
└─────────────────────────────────────┘
```

## 触发机制

### 1. 意图识别阶段

在 `intent_prompt.md` 中，视频创作请求会被识别为：

```json
{
  "intent_id": 3,
  "intent_name": "综合咨询",
  "complexity": "medium",
  "needs_plan": true,
  "routing": "Remotion Skill"
}
```

### 2. 触发关键词

| 类别 | 关键词 |
|------|-------|
| 视频创作 | 视频、video、短视频、宣传片、片头、片尾 |
| 动画效果 | 动画、animation、动效、motion、过渡效果 |
| 动态图形 | motion graphics、动态图表、数据可视化动画 |
| 特定功能 | 字幕动画、打字机效果、文字动画、转场 |
| 技术关键词 | Remotion、React 视频、编程视频 |

### 3. Plan 结构

视频创作任务的推荐 Plan 结构：

```json
{
  "goal": "创建 [视频类型] 视频",
  "steps": [
    {"action": "分析视频需求和风格", "capability": "需求分析"},
    {"action": "设计视频结构和场景", "capability": "创意设计"},
    {"action": "生成 Remotion 代码", "capability": "video_creation"},
    {"action": "提供渲染和预览指引", "capability": "技术指导"}
  ]
}
```

## Skill 使用流程

### Step 1: 加载 Skill

Agent 识别到视频创作意图后，加载 `remotion/SKILL.md` 获取：
- 触发条件验证
- 能力范围说明
- 规则文件索引

### Step 2: 选择规则文件

根据用户具体需求，选择对应的规则文件：

| 用户需求 | 规则文件 |
|---------|---------|
| 基础动画 | animations.md, timing.md |
| 文字效果 | text-animations.md |
| 场景切换 | transitions.md, sequencing.md |
| 数据图表 | charts.md |
| 字幕效果 | display-captions.md |
| 音视频 | audio.md, videos.md |
| 3D 效果 | 3d.md |

### Step 3: 生成代码

基于规则文件的模式生成符合 Remotion 规范的代码：

```tsx
import { useCurrentFrame, useVideoConfig, interpolate } from 'remotion';

export const MyVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  
  const opacity = interpolate(frame, [0, 30], [0, 1]);
  
  return <div style={{ opacity }}>Hello Remotion!</div>;
};
```

### Step 4: 输出结果

提供完整的输出：

1. **需求理解**：确认视频类型、时长、风格
2. **代码生成**：完整的 React 组件
3. **配置说明**：Composition 参数
4. **运行指引**：预览和渲染命令

## 配置文件修改

### config.yaml

添加 video_creation capability：

```yaml
# capability 说明中添加
#   - video_creation: 视频/动画创作（Remotion Skill）
```

### prompt.md

在意图3中添加视频创作场景说明。

### intent_prompt.md

添加视频创作的判断示例（示例 11-14）。

## Skill 注册信息

| 字段 | 值 |
|------|------|
| Skill ID | skill_01UPL1N7CZ2KKxWCWQCs69XE |
| Name | remotion |
| Display Title | Remotion Best Practices - React Video Creation |
| Capability | video_creation |
| 规则文件数量 | 28 个 |

## 测试用例

### 用例1：产品宣传视频

**用户输入**: "帮我创建一个产品宣传视频的动画效果"

**期望流程**:
1. 意图识别 → intent_id: 3, routing: "Remotion Skill"
2. 创建 Plan
3. 加载 Skill，选择 animations.md, timing.md
4. 生成带弹簧动画的产品展示代码
5. 输出代码 + 运行指引

### 用例2：数据可视化动画

**用户输入**: "做一个柱状图动画展示销售数据"

**期望流程**:
1. 意图识别 → intent_id: 3, routing: "Remotion Skill (charts.md)"
2. 创建 Plan
3. 加载 Skill，选择 charts.md
4. 生成动态柱状图代码
5. 输出代码 + 数据配置说明

### 用例3：打字机效果

**用户输入**: "实现一个打字机文字动画效果"

**期望流程**:
1. 意图识别 → intent_id: 3, routing: "Remotion Skill (text-animations.md)"
2. 简单任务，无需 Plan
3. 加载 Skill，选择 text-animations.md
4. 生成打字机效果代码
5. 输出即用代码

## 最佳实践

1. **明确需求**：在生成代码前，确认视频类型、时长、风格
2. **选择合适规则**：根据需求精准选择规则文件
3. **完整输出**：提供代码 + 配置 + 运行指引
4. **遵循规范**：所有动画必须由 `useCurrentFrame()` 驱动
5. **禁止 CSS 动画**：不使用 CSS 或 Tailwind 动画

## 常见问题

### Q: 何时使用 Remotion Skill？
A: 当用户需要创建视频、动画、动态图表等需要编程实现的动态内容时。

### Q: Skill 能生成可直接运行的视频吗？
A: Skill 生成的是 Remotion 代码，用户需要在本地 Node.js 环境中运行和渲染。

### Q: 如何处理复杂的多场景视频？
A: 使用 sequencing.md 和 transitions.md 规则，结合 `<Sequence>` 组件编排多个场景。
