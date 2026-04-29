/**
 * UserControls — Command input bar and execution control buttons
 */

import { useState, useRef } from 'react'

function UserControls({ onCommand, onControl, isExecuting, history }) {
  const [command, setCommand] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const inputRef = useRef(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!command.trim()) return
    onCommand(command.trim())
    setCommand('')
    setShowHistory(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      setShowHistory(false)
    }
    if (e.key === 'ArrowUp' && !command && history?.length > 0) {
      setShowHistory(true)
    }
  }

  const selectHistory = (intent) => {
    setCommand(intent)
    setShowHistory(false)
    inputRef.current?.focus()
  }

  return (
    <div className="controls-section">
      <form onSubmit={handleSubmit} className="command-input-wrapper">
        <span className="command-input-icon">🐾</span>
        <input
          ref={inputRef}
          type="text"
          className="command-input"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => history?.length > 0 && !command && setShowHistory(true)}
          onBlur={() => setTimeout(() => setShowHistory(false), 200)}
          placeholder="Type a command... (e.g., Send I'll be late to Rahul)"
          autoFocus
          id="command-input"
        />

        {/* History dropdown */}
        {showHistory && history?.length > 0 && (
          <div className="history-list">
            {history.map((item, i) => (
              <div
                key={i}
                className="history-item"
                onMouseDown={() => selectHistory(item.intent)}
              >
                <span className="history-intent">{item.intent}</span>
                <span className={`history-outcome ${item.outcome}`}>
                  {item.outcome}
                </span>
              </div>
            ))}
          </div>
        )}
      </form>

      <div className="control-buttons">
        <button
          type="submit"
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={!command.trim() || isExecuting}
          id="btn-execute"
        >
          <span className="btn-icon">▶</span>
          Execute
        </button>

        {isExecuting && (
          <>
            <button
              className="btn"
              onClick={() => onControl('pause')}
              id="btn-pause"
            >
              <span className="btn-icon">⏸</span>
              Pause
            </button>

            <button
              className="btn btn-success"
              onClick={() => onControl('skip')}
              id="btn-skip"
            >
              <span className="btn-icon">⏭</span>
              Skip
            </button>

            <button
              className="btn btn-danger"
              onClick={() => onControl('abort')}
              id="btn-abort"
            >
              <span className="btn-icon">⏹</span>
              Abort
            </button>
          </>
        )}
      </div>
    </div>
  )
}

export default UserControls
