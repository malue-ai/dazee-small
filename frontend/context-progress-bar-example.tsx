/**
 * 上下文进度条示例组件（类似 Cursor）
 * 
 * V6.3 新增：实时显示对话上下文使用情况
 * 
 * 功能：
 * - 实时更新进度条（通过 SSE 事件）
 * - 颜色编码（绿/黄/橙/红）
 * - 显示 token 使用情况
 * - 可选的建议提示
 */

import React, { useState, useEffect } from 'react';

interface ContextUsage {
  currentTokens: number;
  budgetTokens: number;
  usagePercentage: number;
  colorLevel: 'green' | 'yellow' | 'orange' | 'red';
  messageCount: number;
  turnCount: number;
  suggestion?: string;
}

interface ContextProgressBarProps {
  eventSource: EventSource;  // SSE 连接
  position?: 'top' | 'bottom' | 'sidebar';
  showPercentage?: boolean;
  showTokens?: boolean;
}

export const ContextProgressBar: React.FC<ContextProgressBarProps> = ({
  eventSource,
  position = 'top',
  showPercentage = true,
  showTokens = true
}) => {
  const [usage, setUsage] = useState<ContextUsage>({
    currentTokens: 0,
    budgetTokens: 200000,
    usagePercentage: 0,
    colorLevel: 'green',
    messageCount: 0,
    turnCount: 0
  });

  useEffect(() => {
    // 监听上下文使用更新事件
    const handleContextUpdate = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      setUsage({
        currentTokens: data.current_tokens,
        budgetTokens: data.budget_tokens,
        usagePercentage: data.usage_percentage,
        colorLevel: data.color_level,
        messageCount: data.message_count,
        turnCount: data.turn_count,
        suggestion: data.suggestion
      });
    };

    eventSource.addEventListener('context_usage_update', handleContextUpdate);

    return () => {
      eventSource.removeEventListener('context_usage_update', handleContextUpdate);
    };
  }, [eventSource]);

  // 颜色映射
  const colorMap = {
    green: '#22c55e',   // Tailwind green-500
    yellow: '#eab308',  // Tailwind yellow-500
    orange: '#f97316',  // Tailwind orange-500
    red: '#ef4444'      // Tailwind red-500
  };

  const percentage = Math.round(usage.usagePercentage * 100);
  const formattedCurrent = formatTokens(usage.currentTokens);
  const formattedBudget = formatTokens(usage.budgetTokens);

  return (
    <div className={`context-progress-bar ${position}`}>
      {/* 进度条容器 */}
      <div className="flex items-center gap-2 text-sm text-gray-600 px-4 py-2 bg-gray-50 border-b border-gray-200">
        <span className="font-medium">上下文:</span>
        
        {/* 进度条 */}
        <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full transition-all duration-300 ease-in-out"
            style={{
              width: `${percentage}%`,
              backgroundColor: colorMap[usage.colorLevel]
            }}
          />
        </div>
        
        {/* 百分比 */}
        {showPercentage && (
          <span className="font-mono font-medium" style={{ color: colorMap[usage.colorLevel] }}>
            {percentage}%
          </span>
        )}
        
        {/* Token 数值 */}
        {showTokens && (
          <span className="text-xs text-gray-500">
            ({formattedCurrent} / {formattedBudget} tokens)
          </span>
        )}
        
        {/* 可选的建议 */}
        {usage.suggestion && (
          <span className="text-xs text-red-600 font-medium animate-pulse">
            {usage.suggestion}
          </span>
        )}
      </div>
    </div>
  );
};

/**
 * 格式化 token 数值（如 90000 → 90K）
 */
function formatTokens(tokens: number): string {
  if (tokens >= 1000000) {
    return `${(tokens / 1000000).toFixed(1)}M`;
  } else if (tokens >= 1000) {
    return `${Math.round(tokens / 1000)}K`;
  } else {
    return tokens.toString();
  }
}

/**
 * 上下文裁剪通知组件（类似 Cursor）
 */
interface ContextTrimmingNotificationProps {
  eventSource: EventSource;
  autoDismissSeconds?: number;
}

export const ContextTrimmingNotification: React.FC<ContextTrimmingNotificationProps> = ({
  eventSource,
  autoDismissSeconds = 5
}) => {
  const [notification, setNotification] = useState<{
    visible: boolean;
    message: string;
    details?: string;
    tokensSaved?: number;
    learnMoreUrl?: string;
  }>({
    visible: false,
    message: ''
  });

  useEffect(() => {
    const handleTrimmingDone = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      
      setNotification({
        visible: true,
        message: data.display_message,
        details: data.details,
        tokensSaved: data.tokens_saved,
        learnMoreUrl: data.learn_more_url
      });

      // 自动消失
      setTimeout(() => {
        setNotification(prev => ({ ...prev, visible: false }));
      }, autoDismissSeconds * 1000);
    };

    eventSource.addEventListener('context_trimming_done', handleTrimmingDone);

    return () => {
      eventSource.removeEventListener('context_trimming_done', handleTrimmingDone);
    };
  }, [eventSource, autoDismissSeconds]);

  if (!notification.visible) return null;

  return (
    <div className="context-notification fixed top-0 left-0 right-0 z-50 animate-slide-down">
      <div className="max-w-4xl mx-auto mt-4 bg-gray-50 border border-gray-200 rounded-lg shadow-sm p-3">
        <div className="flex items-start gap-2">
          {/* 成功图标 */}
          <span className="text-green-500 text-lg">✓</span>
          
          {/* 消息内容 */}
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-800">
              {notification.message}
            </p>
            {notification.details && (
              <p className="text-xs text-gray-600 mt-1">
                {notification.details}
              </p>
            )}
          </div>
          
          {/* 了解更多链接 */}
          {notification.learnMoreUrl && (
            <a
              href={notification.learnMoreUrl}
              className="text-xs text-blue-600 hover:text-blue-800 underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              了解更多 &gt;
            </a>
          )}
          
          {/* 关闭按钮 */}
          <button
            onClick={() => setNotification(prev => ({ ...prev, visible: false }))}
            className="text-gray-400 hover:text-gray-600"
          >
            ×
          </button>
        </div>
      </div>
    </div>
  );
};

/**
 * 使用示例
 */
export function ChatInterfaceExample() {
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  useEffect(() => {
    // 建立 SSE 连接
    const es = new EventSource('/api/v1/chat/stream?session_id=xxx');
    setEventSource(es);

    return () => {
      es.close();
    };
  }, []);

  if (!eventSource) return null;

  return (
    <div className="chat-interface">
      {/* 上下文进度条（顶部显示） */}
      <ContextProgressBar
        eventSource={eventSource}
        position="top"
        showPercentage={true}
        showTokens={true}
      />
      
      {/* 裁剪通知（临时显示） */}
      <ContextTrimmingNotification
        eventSource={eventSource}
        autoDismissSeconds={5}
      />
      
      {/* 聊天消息区域 */}
      <div className="chat-messages">
        {/* ... 聊天消息列表 ... */}
      </div>
    </div>
  );
}

// CSS 动画（如果使用 Tailwind，可以配置）
const styles = `
@keyframes slide-down {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-slide-down {
  animation: slide-down 0.3s ease-out;
}
`;
