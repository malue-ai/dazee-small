import { AbsoluteFill } from 'remotion';
import { TransitionSeries, linearTiming } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';

// 场景淡入淡出转场示例
// 理想合成尺寸: 1280x720, fps: 30, 时长: 135 帧 (60 + 60 - 15 + 30)

const SceneA: React.FC = () => (
	<AbsoluteFill
		style={{
			backgroundColor: '#1a1a2e',
			justifyContent: 'center',
			alignItems: 'center',
		}}
	>
		<div
			style={{
				color: '#eaf6ff',
				fontSize: 64,
				fontWeight: 700,
				fontFamily: 'sans-serif',
			}}
		>
			Scene A
		</div>
	</AbsoluteFill>
);

const SceneB: React.FC = () => (
	<AbsoluteFill
		style={{
			backgroundColor: '#16213e',
			justifyContent: 'center',
			alignItems: 'center',
		}}
	>
		<div
			style={{
				color: '#e94560',
				fontSize: 64,
				fontWeight: 700,
				fontFamily: 'sans-serif',
			}}
		>
			Scene B
		</div>
	</AbsoluteFill>
);

const SceneC: React.FC = () => (
	<AbsoluteFill
		style={{
			backgroundColor: '#0f3460',
			justifyContent: 'center',
			alignItems: 'center',
		}}
	>
		<div
			style={{
				color: '#00fff5',
				fontSize: 64,
				fontWeight: 700,
				fontFamily: 'sans-serif',
			}}
		>
			Scene C
		</div>
	</AbsoluteFill>
);

export const TransitionsFadeExample: React.FC = () => {
	// 转场时长: 15 帧
	// 总时长计算: 60 + 60 + 30 - 15 - 15 = 120 帧
	const transitionDuration = 15;

	return (
		<TransitionSeries>
			<TransitionSeries.Sequence durationInFrames={60}>
				<SceneA />
			</TransitionSeries.Sequence>

			<TransitionSeries.Transition
				presentation={fade()}
				timing={linearTiming({ durationInFrames: transitionDuration })}
			/>

			<TransitionSeries.Sequence durationInFrames={60}>
				<SceneB />
			</TransitionSeries.Sequence>

			<TransitionSeries.Transition
				presentation={fade()}
				timing={linearTiming({ durationInFrames: transitionDuration })}
			/>

			<TransitionSeries.Sequence durationInFrames={30}>
				<SceneC />
			</TransitionSeries.Sequence>
		</TransitionSeries>
	);
};
