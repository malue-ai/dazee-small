---
name: remotion
description: 使用 React 编程方式创建视频，支持动态图表、数据可视化视频、产品演示与教学视频
homepage: https://remotion.dev
---

# Remotion Skill

使用 [Remotion](https://remotion.dev) 以 React 组件方式生成视频，适合数据可视化、动态图表、产品演示、教学短视频等场景。

## 何时使用

- 用户要求「用这些数据生成一个 XX 秒的视频」
- 需要「动态图表视频」「数据可视化视频」「产品演示视频」「教学/口播视频」
- 需要将表格/图表/文案转成带动画的短视频

## 前置条件

- **Node.js**（建议 v18+）与 **npx**
- 用户环境需已安装 Remotion：`npm init video` 或 `bun create video` 创建项目，或现有项目内 `npm install remotion`

## 工作流程

1. **确认环境**：在用户项目或工作目录中确认存在 Remotion 项目（含 `remotion.config.ts` 或 `remotion.config.js` 及入口如 `src/Root.tsx`）。
2. **生成或修改 Composition**：根据用户需求编写或修改 React 组件（Composition），可接收 `getInputProps()` 传入的数据（如图表数据、文案）。
3. **渲染视频**：在项目根目录执行：
   ```bash
   npx remotion render <entry-point> <composition-id> <output-path>
   ```
   - `entry-point`：入口文件，如 `src/index.tsx` 或 `src/Root.tsx`
   - `composition-id`：在入口中注册的 Composition 的 `id`
   - `output-path`：输出视频路径，如 `./out/video.mp4`
4. **传参与时长**：需传入动态数据时使用 `--props='{"key":"value"}'` 或 `--props=./props.json`；时长由 Composition 的 `durationInFrames` / `fps` 决定。

## 使用示例

- 「用这份销售数据生成一个 30 秒的动态柱状图视频」
- 「把这三页产品要点做成一个 15 秒的演示视频」
- 「根据 CSV 生成趋势变化的折线图视频」

## 输出

- 默认输出为 MP4（H.264）；可用 `--codec` 指定其他编码。
- 输出路径由用户指定或放在项目 `out/` 目录。

## 限制

- 需用户本机已具备 Remotion 项目或同意新建项目；无 Remotion 时需先引导 `npm init video`。
- 复杂动画与长视频渲染耗时较长，可提示用户或使用 `--concurrency` 调整并行度。
