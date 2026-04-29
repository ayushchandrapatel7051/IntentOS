/**
 * StatusBar — Connection status, execution indicator, and skill badges
 */

function StatusBar({ connectionStatus, isExecuting, skills }) {
  return (
    <div className="status-bar">
      {/* Skill badges */}
      {skills && skills.length > 0 && (
        <div className="skill-badges">
          {skills.map((skill) => (
            <span key={skill} className="skill-badge">{skill}</span>
          ))}
        </div>
      )}

      {/* Executing indicator */}
      {isExecuting && (
        <div className="executing-indicator">
          <div className="executing-spinner" />
          Executing
        </div>
      )}

      {/* Connection status */}
      <div className="status-indicator">
        <span className={`status-dot ${connectionStatus}`} />
        {connectionStatus === 'connected' ? 'Live' : 
         connectionStatus === 'connecting' ? 'Connecting...' : 'Offline'}
      </div>
    </div>
  )
}

export default StatusBar
