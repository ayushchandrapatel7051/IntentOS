/**
 * StepTracker — Renders each planned step with status badges
 */

function StepTracker({ steps }) {
  if (!steps || steps.length === 0) return null

  return (
    <div className="step-list">
      {steps.map((step, index) => (
        <div key={step.id} className={`step-item ${step.status}`}>
          <div className={`step-status-dot ${step.status}`} />
          <div className="step-content">
            <div className="step-header">
              <span className="step-skill">{step.skill}</span>
              <span className="step-id">{step.id}</span>
            </div>
            <p className="step-description">{step.description}</p>
            {step.status === 'done' && step.result && (
              <div className="step-result">✓ {step.result}</div>
            )}
            {step.status === 'failed' && step.error && (
              <div className="step-error">✗ {step.error}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export default StepTracker
