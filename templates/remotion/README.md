# Remotion 视频项目

这是一个使用 Remotion 框架的编程视频创作项目模板。Remotion 允许你用 React 代码创建专业的动态视频。

## 快速开始

```bash
# 安装依赖
npm install

# 启动预览（开发模式）
npm start

# 渲染视频
npm run build
```

## 项目结构

```
remotion/
├── README.md              # 本文件
├── package.json           # 依赖配置
├── remotion.config.ts     # Remotion 配置
├── tsconfig.json          # TypeScript 配置
├── src/
│   ├── Root.tsx           # 根组件（Composition 注册）
│   ├── Composition.tsx    # 视频组件（主要编辑区域）
│   └── examples/          # 示例代码
│       ├── text-animations-typewriter.tsx   # 打字机效果
│       ├── text-animations-word-highlight.tsx # 词高亮效果
│       └── charts-bar-chart.tsx             # 柱状图动画
├── animations.md          # 基础动画规则
├── timing.md              # 插值和弹簧动画
├── text-animations.md     # 文字动画
├── charts.md              # 图表动画
├── transitions.md         # 场景转场
├── sequencing.md          # 序列编排
├── audio.md               # 音频处理
├── videos.md              # 视频嵌入
├── 3d.md                  # 3D 内容
├── ...                    # 更多规则文件
└── out/                   # 渲染输出目录
    └── video.mp4          # 生成的视频文件
```

## 核心规则（必读）

### 1. 帧驱动动画

**所有动画必须由 `useCurrentFrame()` 驱动，禁止使用 CSS 动画或 Tailwind 动画类。**

```tsx
import { useCurrentFrame, interpolate } from 'remotion';

const frame = useCurrentFrame();
const opacity = interpolate(frame, [0, 30], [0, 1], {
  extrapolateRight: 'clamp',
});
```

### 2. Composition 配置

在 `Root.tsx` 中配置视频参数：

| 参数 | 说明 | 常用值 |
|------|------|--------|
| `durationInFrames` | 视频总帧数 | fps × 秒数 |
| `fps` | 帧率 | 30 |
| `width` | 视频宽度 | 1280 / 1920 |
| `height` | 视频高度 | 720 / 1080 |

### 3. 弹簧动画

使用 `spring()` 创建自然的物理动画效果：

```tsx
import { spring, useCurrentFrame, useVideoConfig } from 'remotion';

const frame = useCurrentFrame();
const { fps } = useVideoConfig();

// 默认配置（略有弹跳）
const scale = spring({ frame, fps });

// 平滑无弹跳
const smooth = spring({ frame, fps, config: { damping: 200 } });

// 活泼弹跳
const bouncy = spring({ frame, fps, config: { damping: 8 } });
```

### 4. 序列编排

使用 `<Sequence>` 控制元素出现时间：

```tsx
import { Sequence } from 'remotion';

<Sequence from={30} durationInFrames={60} premountFor={fps}>
  <Title />
</Sequence>
```

## 规则文件索引

| 规则文件 | 功能描述 |
|---------|---------|
| [animations.md](animations.md) | 基础动画技能 |
| [timing.md](timing.md) | 插值曲线和弹簧动画 |
| [sequencing.md](sequencing.md) | 序列化模式 |
| [transitions.md](transitions.md) | 场景转场 |
| [text-animations.md](text-animations.md) | 文字动画 |
| [charts.md](charts.md) | 图表动画 |
| [fonts.md](fonts.md) | 字体加载 |
| [audio.md](audio.md) | 音频处理 |
| [videos.md](videos.md) | 视频嵌入 |
| [display-captions.md](display-captions.md) | 字幕显示 |
| [3d.md](3d.md) | 3D 内容 |
| [compositions.md](compositions.md) | 合成配置 |

## 示例代码说明

| 文件 | 说明 |
|------|------|
| `text-animations-typewriter.tsx` | 带光标的打字机效果 |
| `text-animations-word-highlight.tsx` | 荧光笔词高亮效果 |
| `charts-bar-chart.tsx` | 带弹簧动画的柱状图 |

## 渲染命令

```bash
# 默认渲染
npm run build

# 自定义渲染参数
npx remotion render src/Root.tsx MyVideo out/video.mp4 --props='{"title":"Hello"}'

# 渲染指定帧范围
npx remotion render src/Root.tsx MyVideo out/video.mp4 --frames=0-60

# 指定输出格式
npx remotion render src/Root.tsx MyVideo out/video.webm --codec=vp8
```

## 常见问题

### Q: 动画闪烁怎么办？
A: 确保所有动画都由 `useCurrentFrame()` 驱动，禁止使用 CSS 动画、Tailwind 动画类或第三方动画库。

### Q: 如何添加自定义字体？
A: 使用 `@remotion/google-fonts` 或在 CSS 中使用 `@font-face`，详见 [fonts.md](fonts.md)。

### Q: 转场时长如何计算？
A: 转场会重叠相邻场景，总时长 = 场景时长之和 - 转场时长之和，详见 [transitions.md](transitions.md)。

### Q: 3D 内容如何添加？
A: 安装 `@remotion/three`，使用 `<ThreeCanvas>` 包裹 3D 内容，详见 [3d.md](3d.md)。

## 渲染说明

本项目由 `remotion_render` 工具自动渲染，流程：
1. 写入自定义 `Composition.tsx` 代码
2. 更新 `Root.tsx` 中的视频参数
3. 执行 `npx remotion render` 渲染 MP4
4. 上传到 S3 返回下载链接
