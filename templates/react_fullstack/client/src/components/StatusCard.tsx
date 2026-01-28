import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export function StatusCard() {
  const [status, setStatus] = useState<'checking' | 'online' | 'offline'>('checking')

  useEffect(() => {
    api.health()
      .then(() => setStatus('online'))
      .catch(() => setStatus('offline'))
  }, [])

  const statusConfig = {
    checking: { color: 'bg-yellow-100 text-yellow-800', dot: 'bg-yellow-400', text: '检查中...' },
    online: { color: 'bg-green-100 text-green-800', dot: 'bg-green-500', text: '后端服务运行正常' },
    offline: { color: 'bg-red-100 text-red-800', dot: 'bg-red-500', text: '后端服务未连接' },
  }

  const config = statusConfig[status]

  return (
    <div className={`card ${config.color} flex items-center gap-3`}>
      <span className={`w-3 h-3 rounded-full ${config.dot} animate-pulse`} />
      <span className="font-medium">{config.text}</span>
    </div>
  )
}