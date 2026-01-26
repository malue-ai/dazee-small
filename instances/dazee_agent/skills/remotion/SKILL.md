---
name: remotion
description: Remotion 视频创作最佳实践 - 使用 React 进行编程视频创作
metadata:
  tags: remotion, video, react, animation, composition, motion-graphics
  capability: video_creation
  triggers:
    - 视频
    - 动画
    - video
    - animation
    - motion graphics
    - 短视频
    - 宣传片
    - 动态图表
---

# Remotion 视频创作 Skill

这个 Skill 帮助你使用 Remotion 框架进行编程视频创作。Remotion 是一个基于 React 的视频生成框架，可以用代码创建专业的动态视频。

## When to Use（何时调用此 Skill）

当用户请求涉及以下场景时，**必须调用此 Skill**：

### 触发关键词（满足任一即触发）

| 类别 | 关键词 |
|------|-------|
| 视频创作 | "视频"、"video"、"短视频"、"宣传片"、"片头"、"片尾" |
| 动画效果 | "动画"、"animation"、"动效"、"motion"、"过渡效果" |
| 动态图形 | "motion graphics"、"动态图表"、"数据可视化动画" |
| 特定功能 | "字幕动画"、"打字机效果"、"文字动画"、"转场" |
| 技术关键词 | "Remotion"、"React 视频"、"编程视频" |

### 典型用户请求示例

```
✅ "帮我创建一个产品宣传视频的动画效果"
✅ "用 React 做一个数据可视化动画"
✅ "生成一个带字幕的短视频"
✅ "帮我实现一个打字机文字动画效果"
✅ "创建一个柱状图动画展示销售数据"
✅ "做一个视频开场动画"
```

### 不触发此 Skill 的场景

```
❌ 静态图片设计（使用其他工具）
❌ 视频剪辑已有素材（使用剪辑软件）
❌ 简单的 GIF 动图（可能用其他方案）
```

## Capabilities（能力范围）

此 Skill 提供以下专业能力：

| 能力类别 | 具体功能 | 对应规则文件 |
|---------|---------|-------------|
| **基础动画** | interpolate、spring、缓动函数 | animations.md, timing.md |
| **文字动画** | 打字机、词高亮、文字淡入淡出 | text-animations.md |
| **序列编排** | 场景切换、时间序列、延迟播放 | sequencing.md |
| **转场效果** | 场景过渡、淡入淡出、滑动 | transitions.md |
| **数据可视化** | 动态图表、柱状图、折线图动画 | charts.md |
| **字幕处理** | SRT 导入、TikTok 风格字幕 | display-captions.md, import-srt-captions.md |
| **音视频处理** | 音频同步、视频嵌入、音量控制 | audio.md, videos.md |
| **3D 内容** | Three.js 集成、React Three Fiber | 3d.md |
| **资源管理** | 字体加载、图片嵌入、静态资源 | fonts.md, images.md, assets.md |

## How to Use（使用方法）

### Step 1: 理解用户需求

分析用户的视频创作需求：
- 视频类型：宣传片、数据展示、教程、动态海报
- 时长：短片（<30s）、中等（30s-2min）、长片（>2min）
- 风格：商务、科技、活泼、简约
- 核心元素：文字、图表、图片、3D

### Step 2: 选择合适的规则文件

根据需求阅读对应的规则文件获取代码示例：

```
用户需求 → 对应规则
├── "文字动画" → text-animations.md
├── "数据图表" → charts.md
├── "场景切换" → transitions.md, sequencing.md
├── "字幕效果" → display-captions.md
├── "背景音乐" → audio.md
└── "3D效果" → 3d.md
```

### Step 3: 生成 Remotion 代码

基于规则文件的模式生成符合 Remotion 规范的 React 代码：

```tsx
// 标准 Remotion 组件结构
import { useCurrentFrame, useVideoConfig, interpolate, spring } from 'remotion';

export const MyVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  
  // 使用 interpolate 创建动画
  const opacity = interpolate(frame, [0, 30], [0, 1]);
  
  return <div style={{ opacity }}>...</div>;
};
```

## 核心规则速查

### 1. 动画驱动（animations.md）

```tsx
// 所有动画必须由 useCurrentFrame() 驱动
const frame = useCurrentFrame();
const opacity = interpolate(frame, [0, 30], [0, 1], {
  extrapolateRight: 'clamp',
});

// ❌ 禁止 CSS 动画
// ❌ 禁止 Tailwind 动画类
```

### 2. 弹簧动画（timing.md）

```tsx
const scale = spring({
  frame,
  fps,
  config: { damping: 12, stiffness: 100 },
});
```

### 3. 序列编排（sequencing.md）

```tsx
<AbsoluteFill>
  <Sequence from={0} durationInFrames={90}>
    <Scene1 />
  </Sequence>
  <Sequence from={90} durationInFrames={120}>
    <Scene2 />
  </Sequence>
</AbsoluteFill>
```

### 4. 字体加载（fonts.md）

```tsx
import { loadFont } from '@remotion/google-fonts/Inter';
const { fontFamily } = loadFont();
```

## 输出规范

当生成 Remotion 代码时，必须遵循：

1. **完整的组件结构**：包含所有必要的 import
2. **注释说明**：解释关键动画参数
3. **Composition 配置**：提供建议的 fps、尺寸、时长
4. **渲染指令**：说明如何预览和渲染

## 规则文件索引

| 规则文件 | 功能描述 |
|---------|---------|
| [rules/animations.md](rules/animations.md) | 基础动画技能 |
| [rules/timing.md](rules/timing.md) | 插值曲线和弹簧动画 |
| [rules/sequencing.md](rules/sequencing.md) | 序列化模式 |
| [rules/transitions.md](rules/transitions.md) | 场景转场 |
| [rules/text-animations.md](rules/text-animations.md) | 文字动画 |
| [rules/charts.md](rules/charts.md) | 图表动画 |
| [rules/fonts.md](rules/fonts.md) | 字体加载 |
| [rules/audio.md](rules/audio.md) | 音频处理 |
| [rules/videos.md](rules/videos.md) | 视频嵌入 |
| [rules/display-captions.md](rules/display-captions.md) | 字幕显示 |
| [rules/3d.md](rules/3d.md) | 3D 内容 |
| [rules/compositions.md](rules/compositions.md) | 合成配置 |

## 与 Plan 机制的集成

当用户请求视频创作任务时，建议的 Plan 结构：

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

## Limitations

- 需要 Node.js 环境运行 Remotion
- 视频渲染需要一定计算资源
- 复杂 3D 效果需要额外依赖包
- 最终渲染需要用户本地执行
