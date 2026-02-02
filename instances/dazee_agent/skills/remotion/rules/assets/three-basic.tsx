import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring } from 'remotion';
import { ThreeCanvas } from '@remotion/three';

// React Three Fiber 基础示例
// 理想合成尺寸: 1280x720, fps: 30, 时长: 120 帧 (4 秒)
// 需要安装: npx remotion add @remotion/three

const RotatingCube: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	// 旋转动画 - 必须由 useCurrentFrame() 驱动
	const rotationY = frame * 0.03;
	const rotationX = frame * 0.02;

	// 缩放入场动画
	const scale = spring({
		frame,
		fps,
		config: { damping: 12, stiffness: 100 },
	});

	return (
		<mesh rotation={[rotationX, rotationY, 0]} scale={scale * 2}>
			<boxGeometry args={[1, 1, 1]} />
			<meshStandardMaterial color="#4a9eff" metalness={0.5} roughness={0.2} />
		</mesh>
	);
};

const FloatingSphere: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	// 上下浮动动画
	const floatY = Math.sin(frame * 0.1) * 0.5;

	// 延迟入场
	const scale = spring({
		frame: frame - 15,
		fps,
		config: { damping: 15, stiffness: 80 },
	});

	return (
		<mesh position={[-2.5, floatY, 0]} scale={scale}>
			<sphereGeometry args={[0.6, 32, 32]} />
			<meshStandardMaterial color="#e94560" metalness={0.8} roughness={0.1} />
		</mesh>
	);
};

const SpinningTorus: React.FC = () => {
	const frame = useCurrentFrame();
	const { fps } = useVideoConfig();

	// 旋转动画
	const rotationZ = frame * 0.05;

	// 延迟入场
	const scale = spring({
		frame: frame - 30,
		fps,
		config: { damping: 15, stiffness: 80 },
	});

	return (
		<mesh position={[2.5, 0, 0]} rotation={[Math.PI / 4, 0, rotationZ]} scale={scale}>
			<torusGeometry args={[0.5, 0.2, 16, 32]} />
			<meshStandardMaterial color="#00fff5" metalness={0.6} roughness={0.3} />
		</mesh>
	);
};

export const ThreeBasicExample: React.FC = () => {
	const { width, height } = useVideoConfig();
	const frame = useCurrentFrame();

	// 相机缓慢推进
	const cameraZ = interpolate(frame, [0, 120], [8, 6], {
		extrapolateRight: 'clamp',
	});

	return (
		<AbsoluteFill style={{ backgroundColor: '#0a0a0a' }}>
			<ThreeCanvas
				width={width}
				height={height}
				camera={{ position: [0, 0, cameraZ], fov: 50 }}
			>
				{/* 环境光 */}
				<ambientLight intensity={0.4} />

				{/* 主光源 */}
				<directionalLight position={[5, 5, 5]} intensity={0.8} />

				{/* 补光 */}
				<pointLight position={[-5, -5, 5]} intensity={0.3} color="#4a9eff" />

				{/* 3D 物体 */}
				<RotatingCube />
				<FloatingSphere />
				<SpinningTorus />
			</ThreeCanvas>

			{/* 标题叠加层 */}
			<div
				style={{
					position: 'absolute',
					bottom: 60,
					left: 0,
					right: 0,
					textAlign: 'center',
					color: '#ffffff',
					fontSize: 32,
					fontWeight: 600,
					fontFamily: 'sans-serif',
					textShadow: '0 2px 10px rgba(0,0,0,0.5)',
				}}
			>
				Three.js in Remotion
			</div>
		</AbsoluteFill>
	);
};
