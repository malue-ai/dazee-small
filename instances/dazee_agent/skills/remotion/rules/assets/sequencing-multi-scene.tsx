import {
	AbsoluteFill,
	Sequence,
	useCurrentFrame,
	useVideoConfig,
	interpolate,
	spring,
} from 'remotion';

// 多场景序列编排示例
// 理想合成尺寸: 1280x720, fps: 30, 时长: 180 帧 (6 秒)

const Intro: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	const scale = spring({
		frame,
		fps,
		config: { damping: 12, stiffness: 100 },
	});

	const opacity = interpolate(frame, [0, 15], [0, 1], {
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
					color: '#ffffff',
					fontSize: 80,
					fontWeight: 700,
					fontFamily: 'sans-serif',
				}}
			>
				Welcome
			</div>
		</AbsoluteFill>
	);
};

const MainContent: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	// 三个要点依次出现
	const items = ['Feature One', 'Feature Two', 'Feature Three'];

	return (
		<AbsoluteFill
			style={{
				backgroundColor: '#1a1a2e',
				justifyContent: 'center',
				alignItems: 'center',
				flexDirection: 'column',
				gap: 30,
			}}
		>
			{items.map((item, index) => {
				const delay = index * 20;
				const itemSpring = spring({
					frame: frame - delay,
					fps,
					config: { damping: 15, stiffness: 100 },
				});

				const translateX = interpolate(itemSpring, [0, 1], [-100, 0]);
				const opacity = interpolate(itemSpring, [0, 1], [0, 1]);

				return (
					<div
						key={item}
						style={{
							opacity,
							transform: `translateX(${translateX}px)`,
							color: '#e94560',
							fontSize: 48,
							fontWeight: 600,
							fontFamily: 'sans-serif',
						}}
					>
						• {item}
					</div>
				);
			})}
		</AbsoluteFill>
	);
};

const Outro: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps, durationInFrames } = useVideoConfig();

	// 淡入效果
	const fadeIn = interpolate(frame, [0, 15], [0, 1], {
		extrapolateRight: 'clamp',
	});

	// 淡出效果（最后 15 帧）
	const fadeOut = interpolate(
		frame,
		[durationInFrames - 15, durationInFrames],
		[1, 0],
		{
			extrapolateLeft: 'clamp',
		}
	);

	const opacity = Math.min(fadeIn, fadeOut);

	return (
		<AbsoluteFill
			style={{
				backgroundColor: '#16213e',
				justifyContent: 'center',
				alignItems: 'center',
			}}
		>
			<div
				style={{
					opacity,
					color: '#00fff5',
					fontSize: 64,
					fontWeight: 700,
					fontFamily: 'sans-serif',
					textAlign: 'center',
				}}
			>
				Thank You!
			</div>
		</AbsoluteFill>
	);
};

export const SequencingMultiSceneExample: React.FC = () => {
	const { fps } = useVideoConfig();

	return (
		<AbsoluteFill>
			{/* 场景 1: 开场 (0-60 帧，2秒) */}
			<Sequence from={0} durationInFrames={60} premountFor={fps}>
				<Intro />
			</Sequence>

			{/* 场景 2: 主要内容 (45-135 帧，与开场重叠 15 帧) */}
			<Sequence from={45} durationInFrames={90} premountFor={fps}>
				<MainContent />
			</Sequence>

			{/* 场景 3: 结尾 (120-180 帧，与主内容重叠 15 帧) */}
			<Sequence from={120} durationInFrames={60} premountFor={fps}>
				<Outro />
			</Sequence>
		</AbsoluteFill>
	);
};
