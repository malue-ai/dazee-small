import {
	AbsoluteFill,
	useCurrentFrame,
	useVideoConfig,
	interpolate,
	spring,
	Sequence,
} from 'remotion';

// 弹簧动画效果示例
// 理想合成尺寸: 1280x720, fps: 30, 时长: 150 帧 (5 秒)

// 不同弹簧配置的对比演示
const SpringDemo: React.FC<{
	label: string;
	color: string;
	config: { damping?: number; stiffness?: number; mass?: number };
	delay: number;
}> = ({ label, color, config, delay }) => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	const progress = spring({
		frame: frame - delay,
		fps,
		config,
	});

	// 从左侧滑入 + 缩放
	const translateX = interpolate(progress, [0, 1], [-200, 0]);
	const scale = progress;

	return (
		<div
			style={{
				display: 'flex',
				alignItems: 'center',
				gap: 30,
				marginBottom: 20,
			}}
		>
			<div
				style={{
					width: 200,
					color: '#888888',
					fontSize: 18,
					fontFamily: 'monospace',
					textAlign: 'right',
				}}
			>
				{label}
			</div>
			<div
				style={{
					width: 80,
					height: 80,
					borderRadius: 16,
					backgroundColor: color,
					transform: `translateX(${translateX}px) scale(${scale})`,
					display: 'flex',
					justifyContent: 'center',
					alignItems: 'center',
					boxShadow: `0 10px 30px ${color}40`,
				}}
			/>
			<div
				style={{
					flex: 1,
					height: 4,
					backgroundColor: '#333333',
					borderRadius: 2,
					overflow: 'hidden',
				}}
			>
				<div
					style={{
						width: `${progress * 100}%`,
						height: '100%',
						backgroundColor: color,
						borderRadius: 2,
					}}
				/>
			</div>
		</div>
	);
};

// 弹跳球动画
const BouncingBall: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps, durationInFrames } = useVideoConfig();

	// 入场弹簧
	const enterSpring = spring({
		frame,
		fps,
		config: { damping: 8, stiffness: 150 },
	});

	// 出场弹簧
	const exitSpring = spring({
		frame: frame - (durationInFrames - fps),
		fps,
		config: { damping: 200 },
	});

	const scale = enterSpring - exitSpring;

	// 持续弹跳效果
	const bounceY = Math.sin(frame * 0.15) * 20 * scale;

	// 挤压拉伸效果
	const squash = 1 + Math.sin(frame * 0.15) * 0.1;
	const stretch = 1 - Math.sin(frame * 0.15) * 0.1;

	return (
		<div
			style={{
				width: 100,
				height: 100,
				borderRadius: '50%',
				background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
				transform: `translateY(${bounceY}px) scale(${scale * stretch}, ${scale * squash})`,
				boxShadow: '0 20px 40px rgba(102, 126, 234, 0.4)',
			}}
		/>
	);
};

export const SpringBounceExample: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	// 标题入场动画
	const titleOpacity = interpolate(frame, [0, 20], [0, 1], {
		extrapolateRight: 'clamp',
	});

	const titleY = spring({
		frame,
		fps,
		config: { damping: 15, stiffness: 100 },
	});

	const titleTranslateY = interpolate(titleY, [0, 1], [-50, 0]);

	return (
		<AbsoluteFill
			style={{
				backgroundColor: '#0a0a0a',
				padding: 60,
				fontFamily: 'sans-serif',
			}}
		>
			{/* 标题 */}
			<div
				style={{
					opacity: titleOpacity,
					transform: `translateY(${titleTranslateY}px)`,
					color: '#ffffff',
					fontSize: 48,
					fontWeight: 700,
					marginBottom: 50,
					textAlign: 'center',
				}}
			>
				Spring Animation Configs
			</div>

			{/* 弹簧配置对比 */}
			<div style={{ flex: 1 }}>
				<SpringDemo
					label="smooth (damping: 200)"
					color="#4a9eff"
					config={{ damping: 200 }}
					delay={0}
				/>
				<SpringDemo
					label="snappy (d:20, s:200)"
					color="#00fff5"
					config={{ damping: 20, stiffness: 200 }}
					delay={15}
				/>
				<SpringDemo
					label="bouncy (damping: 8)"
					color="#e94560"
					config={{ damping: 8 }}
					delay={30}
				/>
				<SpringDemo
					label="heavy (d:15, s:80, m:2)"
					color="#f5af19"
					config={{ damping: 15, stiffness: 80, mass: 2 }}
					delay={45}
				/>
			</div>

			{/* 弹跳球演示 */}
			<div
				style={{
					display: 'flex',
					justifyContent: 'center',
					alignItems: 'center',
					height: 200,
				}}
			>
				<Sequence from={60} durationInFrames={90} premountFor={fps}>
					<BouncingBall />
				</Sequence>
			</div>
		</AbsoluteFill>
	);
};
