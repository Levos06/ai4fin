import React from 'react'
import './ToolStepViewer.css'

function ToolStepViewer({ step }) {
  if (!step) return null

  return (
    <div className="tool-step-viewer">
      <div className="tool-step-header">
        <span className="tool-step-number">Шаг {step.step_number}</span>
        {step.tool_name && (
          <span className="tool-step-name">{step.tool_name}</span>
        )}
      </div>
      {step.tool_input && (
        <div className="tool-step-input">
          <strong>Входные данные:</strong>
          <pre>{JSON.stringify(step.tool_input, null, 2)}</pre>
        </div>
      )}
      {step.tool_result && step.tool_result.success !== undefined && (
        <div className={`tool-step-result ${step.tool_result.success ? 'success' : 'error'}`}>
          {step.tool_result.success ? '✓' : '✗'} 
          {step.tool_result.success ? 'Успешно' : 'Ошибка'}
        </div>
      )}
    </div>
  )
}

export default ToolStepViewer

