import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';

// 这个文件会被 remotion_render 工具替换为用户生成的代码
// 以下是一个简单的占位符示例

export const MyVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // 淡入效果
  const opacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: 'clamp',
  });

  // 缩放效果
  const scale = interpolate(frame, [0, 30], [0.8, 1], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#0a0a0a',
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <div
        style={{
          opacity,
          transform: `scale(${scale})`,
          color: 'white',
          fontSize: 72,
          fontWeight: 700,
          fontFamily: 'sans-serif',
          textAlign: 'center',
        }}
      >
        Hello Remotion!
      </div>
    </AbsoluteFill>
  );
};
