/**
 * LiveLogs — Terminal-style log panel with auto-scroll
 */

import { useEffect, useRef } from 'react'

function LiveLogs({ logs }) {
  const containerRef = useRef(null)

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs])

  const formatTime = (timestamp) => {
    if (!timestamp) return '--:--:--'
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', { 
      hour12: false, 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    })
  }

  if (!logs || logs.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-icon">📡</span>
        <p>Waiting for output...</p>
        <p className="empty-hint">Logs will stream here in real time</p>
      </div>
    )
  }

  return (
    <div className="logs-container" ref={containerRef}>
      {logs.map((log, index) => (
        <div key={index} className="log-entry">
          <span className="log-time">{formatTime(log.timestamp)}</span>
          <span className={`log-level ${log.level}`}>{log.level}</span>
          <span className={`log-message ${log.stream === 'stderr' ? 'stderr' : ''}`}>
            {log.message}
          </span>
        </div>
      ))}
    </div>
  )
}

export default LiveLogs
