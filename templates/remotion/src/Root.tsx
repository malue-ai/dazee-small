import { Composition } from 'remotion';
import { MyVideo } from './Composition';

// 视频配置 - 这些值会被 remotion_render 工具动态更新
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="MyVideo"
        component={MyVideo}
        durationInFrames={150}
        fps={30}
        width={1280}
        height={720}
      />
    </>
  );
};
