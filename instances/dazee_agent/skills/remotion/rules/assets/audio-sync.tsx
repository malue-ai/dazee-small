import {
	AbsoluteFill,
	Sequence,
	useCurrentFrame,
	useVideoConfig,
	interpolate,
	spring,
	staticFile,
} from 'remotion';
import { Audio } from '@remotion/media';

// 音频同步示例
// 理想合成尺寸: 1280x720, fps: 30, 时长: 150 帧 (5 秒)
// 注意：需要在 public 目录放置 audio.mp3 文件

const VisualIndicator: React.FC<{ beat: number }> = ({ beat }) => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	// 每个 beat 的动画
	const beatFrame = frame - beat * 15; // 假设每 0.5 秒一个节拍
	const scale = spring({
		frame: beatFrame,
		fps,
		config: { damping: 8, stiffness: 200 },
	});

	const opacity = interpolate(beatFrame, [0, 15], [1, 0.3], {
		extrapolateLeft: 'clamp',
		extrapolateRight: 'clamp',
	});

	return (
		<div
			style={{
				width: 100,
				height: 100,
				borderRadius: '50%',
				backgroundColor: '#e94560',
				transform: `scale(${scale})`,
				opacity,
			}}
		/>
	);
};

const VolumeBar: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	// 模拟音量波形
	const bars = Array.from({ length: 12 }, (_, i) => {
		const phase = (frame * 0.3 + i * 0.5) % (Math.PI * 2);
		const height = 30 + Math.sin(phase) * 50 + Math.random() * 20;

		return (
			<div
				key={i}
				style={{
					width: 12,
					height: Math.max(10, height),
					backgroundColor: '#00fff5',
					borderRadius: 6,
					transition: 'none', // 禁止 CSS 过渡
				}}
			/>
		);
	});

	return (
		<div
			style={{
				display: 'flex',
				alignItems: 'center',
				gap: 8,
				height: 100,
			}}
		>
			{bars}
		</div>
	);
};

export const AudioSyncExample: React.FC = () => {
	const { fps, durationInFrames } = useVideoConfig();

	// 音量淡入淡出
	const volumeCallback = (f: number) => {
		const fadeIn = interpolate(f, [0, fps], [0, 1], {
			extrapolateRight: 'clamp',
		});
		const fadeOut = interpolate(
			f,
			[durationInFrames - fps, durationInFrames],
			[1, 0],
			{
				extrapolateLeft: 'clamp',
			}
		);
		return Math.min(fadeIn, fadeOut) * 0.8; // 最大音量 80%
	};

	return (
		<AbsoluteFill
			style={{
				backgroundColor: '#0a0a0a',
				justifyContent: 'center',
				alignItems: 'center',
				flexDirection: 'column',
				gap: 60,
			}}
		>
			{/* 背景音乐 - 使用动态音量 */}
			<Audio
				src={staticFile('audio.mp3')}
				volume={volumeCallback}
				// trimBefore={0}
				// trimAfter={durationInFrames}
			/>

			{/* 标题 */}
			<div
				style={{
					color: '#ffffff',
					fontSize: 48,
					fontWeight: 700,
					fontFamily: 'sans-serif',
				}}
			>
				Audio Sync Demo
			</div>

			{/* 音量可视化 */}
			<VolumeBar />

			{/* 节拍指示器 */}
			<div
				style={{
					display: 'flex',
					gap: 30,
				}}
			>
				{[0, 1, 2, 3, 4].map((beat) => (
					<Sequence
						key={beat}
						from={beat * 15}
						durationInFrames={30}
						layout="none"
					>
						<VisualIndicator beat={beat} />
					</Sequence>
				))}
			</div>

			{/* 提示文字 */}
			<div
				style={{
					color: '#888888',
					fontSize: 20,
					fontFamily: 'sans-serif',
				}}
			>
				需要在 public 目录放置 audio.mp3 文件
			</div>
		</AbsoluteFill>
	);
};
