import { Config } from '@remotion/cli/config';

// Remotion 配置文件
// 参考: https://www.remotion.dev/docs/config

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);

// 渲染性能优化
Config.setConcurrency(1);

// 输出目录
Config.setOutputLocation('out');
