/**
 * ReasoningPanel — Displays AI chain-of-thought reasoning
 */

function ReasoningPanel({ reasoning }) {
  if (!reasoning || reasoning.length === 0) return null

  return (
    <div className="reasoning-list">
      {reasoning.map((item, index) => (
        <div key={index} className="reasoning-item">
          <div className="reasoning-step-id">{item.stepId}</div>
          <p className="reasoning-text">{item.text}</p>
        </div>
      ))}
    </div>
  )
}

export default ReasoningPanel
