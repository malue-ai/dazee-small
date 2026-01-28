import { StatusCard } from '../components/StatusCard'

export function HomePage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      {/* 头部 */}
      <header className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          🚀 React 全栈模板
        </h1>
        <p className="text-gray-500 text-lg">
          基于 Vite + React + TypeScript + TailwindCSS v4
        </p>
      </header>

      {/* 状态卡片 */}
      <StatusCard />

      {/* 功能区域 */}
      <div className="card mt-8">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">
          📝 开始开发
        </h2>
        <p className="text-gray-600 mb-4">
          这是一个标准的 React 全栈项目模板，您可以在此基础上快速开发业务功能。
        </p>
        <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm text-gray-700">
          <p className="mb-2">项目结构：</p>
          <ul className="space-y-1 ml-4">
            <li>• <code>client/src/components/</code> - 组件</li>
            <li>• <code>client/src/pages/</code> - 页面</li>
            <li>• <code>client/src/hooks/</code> - Hooks</li>
            <li>• <code>client/src/lib/</code> - 工具函数</li>
            <li>• <code>server/index.ts</code> - 后端 API</li>
            <li>• <code>shared/</code> - 共享类型</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
