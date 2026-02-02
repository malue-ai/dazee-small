import { AbsoluteFill } from 'remotion';
import { TransitionSeries, springTiming } from '@remotion/transitions';
import { slide } from '@remotion/transitions/slide';

// 滑动转场效果示例
// 理想合成尺寸: 1280x720, fps: 30

const Card: React.FC<{
	title: string;
	color: string;
	bgColor: string;
}> = ({ title, color, bgColor }) => (
	<AbsoluteFill
		style={{
			backgroundColor: bgColor,
			justifyContent: 'center',
			alignItems: 'center',
		}}
	>
		<div
			style={{
				backgroundColor: 'rgba(255, 255, 255, 0.1)',
				padding: '60px 100px',
				borderRadius: 24,
				backdropFilter: 'blur(10px)',
			}}
		>
			<div
				style={{
					color,
					fontSize: 72,
					fontWeight: 700,
					fontFamily: 'sans-serif',
				}}
			>
				{title}
			</div>
		</div>
	</AbsoluteFill>
);

export const TransitionsSlideExample: React.FC = () => {
	// 使用弹簧动画的滑动转场
	const springConfig = { damping: 200 };

	return (
		<TransitionSeries>
			{/* 第一个场景：从右侧滑入 */}
			<TransitionSeries.Sequence durationInFrames={60}>
				<Card title="Step 1" color="#ffffff" bgColor="#667eea" />
			</TransitionSeries.Sequence>

			{/* 从左侧滑动转场 */}
			<TransitionSeries.Transition
				presentation={slide({ direction: 'from-left' })}
				timing={springTiming({
					config: springConfig,
					durationInFrames: 25,
				})}
			/>

			<TransitionSeries.Sequence durationInFrames={60}>
				<Card title="Step 2" color="#ffffff" bgColor="#764ba2" />
			</TransitionSeries.Sequence>

			{/* 从底部滑动转场 */}
			<TransitionSeries.Transition
				presentation={slide({ direction: 'from-bottom' })}
				timing={springTiming({
					config: springConfig,
					durationInFrames: 25,
				})}
			/>

			<TransitionSeries.Sequence durationInFrames={60}>
				<Card title="Step 3" color="#ffffff" bgColor="#f093fb" />
			</TransitionSeries.Sequence>

			{/* 从右侧滑动转场 */}
			<TransitionSeries.Transition
				presentation={slide({ direction: 'from-right' })}
				timing={springTiming({
					config: springConfig,
					durationInFrames: 25,
				})}
			/>

			<TransitionSeries.Sequence durationInFrames={45}>
				<Card title="Done!" color="#ffffff" bgColor="#f5576c" />
			</TransitionSeries.Sequence>
		</TransitionSeries>
	);
};
