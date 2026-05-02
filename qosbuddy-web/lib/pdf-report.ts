import { jsPDF } from 'jspdf'
import { RCAEvent } from './websocket'

export function generateIncidentReport(event: RCAEvent): jsPDF {
  const doc = new jsPDF()
  const pageWidth = doc.internal.pageSize.getWidth()
  const margin = 20
  let y = 20

  // Header
  doc.setFillColor(15, 23, 42) // navy-900
  doc.rect(0, 0, pageWidth, 50, 'F')
  
  doc.setTextColor(59, 130, 246) // accent-blue
  doc.setFontSize(24)
  doc.setFont('helvetica', 'bold')
  doc.text('QoSBuddy', margin, 30)
  
  doc.setTextColor(255, 255, 255)
  doc.setFontSize(14)
  doc.text('Incident Report', margin, 42)

  y = 70

  // Report metadata
  doc.setTextColor(100, 100, 100)
  doc.setFontSize(10)
  doc.setFont('helvetica', 'normal')
  doc.text(`Report ID: ${event.rca_event_id}`, pageWidth - margin - 60, y)
  doc.text(`Generated: ${new Date().toLocaleString()}`, pageWidth - margin - 60, y + 5)
  
  y += 30

  // Incident Summary Section
  doc.setTextColor(15, 23, 42)
  doc.setFontSize(16)
  doc.setFont('helvetica', 'bold')
  doc.text('Incident Summary', margin, y)
  
  y += 10
  doc.setDrawColor(59, 130, 246)
  doc.line(margin, y, pageWidth - margin, y)
  y += 15

  // Details grid
  doc.setFontSize(11)
  const details = [
    ['Cell ID:', event.cell_id],
    ['Region:', event.region || 'N/A'],
    ['Vendor:', event.vendor || 'N/A'],
    ['Band:', event.nr_band || 'N/A'],
    ['Network Slice:', event.network_slice || 'N/A'],
    ['Timestamp:', new Date(event.timestamp).toLocaleString()],
    ['Severity:', event.anomaly_severity.toUpperCase()],
    ['Anomaly Score:', event.anomaly_score?.toFixed(3) || 'N/A']
  ]

  doc.setFont('helvetica', 'bold')
  details.forEach(([label, value]) => {
    doc.setTextColor(100, 100, 100)
    doc.text(label as string, margin, y)
    doc.setTextColor(15, 23, 42)
    doc.setFont('helvetica', 'normal')
    doc.text(String(value), margin + 40, y)
    doc.setFont('helvetica', 'bold')
    y += 8
  })

  y += 15

  // Root Cause Analysis Section
  doc.setTextColor(15, 23, 42)
  doc.setFontSize(16)
  doc.setFont('helvetica', 'bold')
  doc.text('Root Cause Analysis', margin, y)
  
  y += 10
  doc.setDrawColor(59, 130, 246)
  doc.line(margin, y, pageWidth - margin, y)
  y += 15

  if (event.rca) {
    doc.setFontSize(11)
    
    doc.setTextColor(100, 100, 100)
    doc.setFont('helvetica', 'bold')
    doc.text('Primary Cause:', margin, y)
    y += 8
    
    doc.setTextColor(15, 23, 42)
    doc.setFont('helvetica', 'normal')
    const cause = event.rca.primary_cause || 'Unknown'
    const causeLines = doc.splitTextToSize(cause, pageWidth - 2 * margin)
    doc.text(causeLines, margin, y)
    y += causeLines.length * 6 + 10

    if (event.rca.confidence) {
      doc.setTextColor(100, 100, 100)
      doc.setFont('helvetica', 'bold')
      doc.text(`Confidence: ${(event.rca.confidence * 100).toFixed(1)}%`, margin, y)
      y += 15
    }

    if (event.rca.explanation) {
      doc.setTextColor(100, 100, 100)
      doc.setFont('helvetica', 'bold')
      doc.text('Explanation:', margin, y)
      y += 8
      
      doc.setTextColor(15, 23, 42)
      doc.setFont('helvetica', 'normal')
      const explanation = event.rca.explanation
      const expLines = doc.splitTextToSize(explanation, pageWidth - 2 * margin)
      doc.text(expLines, margin, y)
      y += expLines.length * 6 + 15
    }
  }

  // KPI Snapshot Section
  if (event.kpi_snapshot && Object.keys(event.kpi_snapshot).length > 0) {
    if (y > 200) {
      doc.addPage()
      y = 30
    }

    doc.setTextColor(15, 23, 42)
    doc.setFontSize(16)
    doc.setFont('helvetica', 'bold')
    doc.text('KPI Snapshot', margin, y)
    
    y += 10
    doc.setDrawColor(59, 130, 246)
    doc.line(margin, y, pageWidth - margin, y)
    y += 15

    doc.setFontSize(10)
    let col = 0
    const colWidth = (pageWidth - 2 * margin) / 2
    
    Object.entries(event.kpi_snapshot).forEach(([key, value]) => {
      const x = margin + (col * colWidth)
      
      doc.setTextColor(100, 100, 100)
      doc.setFont('helvetica', 'bold')
      doc.text(`${key}:`, x, y)
      
      doc.setTextColor(15, 23, 42)
      doc.setFont('helvetica', 'normal')
      doc.text(typeof value === 'number' ? value.toFixed(3) : String(value), x + 50, y)
      
      col = (col + 1) % 2
      if (col === 0) y += 8
    })
    
    y += 20
  }

  // AI Remediation Section
  if (event.remediation) {
    if (y > 180) {
      doc.addPage()
      y = 30
    }

    doc.setTextColor(15, 23, 42)
    doc.setFontSize(16)
    doc.setFont('helvetica', 'bold')
    doc.text('AI Remediation Recommendation', margin, y)
    
    y += 10
    doc.setDrawColor(6, 182, 212) // accent-cyan
    doc.line(margin, y, pageWidth - margin, y)
    y += 15

    doc.setFontSize(11)
    
    doc.setTextColor(100, 100, 100)
    doc.setFont('helvetica', 'bold')
    doc.text('Recommended Action:', margin, y)
    y += 8
    
    doc.setTextColor(6, 182, 212)
    doc.setFont('helvetica', 'bold')
    const action = event.remediation.primary_action?.action || event.remediation.cause
    const actionLines = doc.splitTextToSize(action, pageWidth - 2 * margin)
    doc.text(actionLines, margin, y)
    y += actionLines.length * 6 + 10

    if (event.remediation.primary_action?.steps) {
      doc.setTextColor(100, 100, 100)
      doc.setFont('helvetica', 'bold')
      doc.text('Action Steps:', margin, y)
      y += 8
      
      doc.setTextColor(15, 23, 42)
      doc.setFont('helvetica', 'normal')
      event.remediation.primary_action.steps.forEach((step, idx) => {
        doc.text(`${idx + 1}. ${step}`, margin + 5, y)
        y += 6
      })
      y += 10
    }

    if (event.remediation.primary_action) {
      const { priority, effort, eta_hours } = event.remediation.primary_action
      doc.setTextColor(100, 100, 100)
      doc.setFont('helvetica', 'bold')
      doc.text(`Priority: ${priority} | Effort: ${effort} | ETA: ${eta_hours}h`, margin, y)
    }
  }

  // Footer
  const pageCount = doc.getNumberOfPages()
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i)
    doc.setTextColor(150, 150, 150)
    doc.setFontSize(9)
    doc.setFont('helvetica', 'normal')
    doc.text(
      `QoSBuddy Incident Report | Page ${i} of ${pageCount} | Confidential`,
      pageWidth / 2,
      doc.internal.pageSize.getHeight() - 10,
      { align: 'center' }
    )
  }

  return doc
}

export function downloadReport(event: RCAEvent) {
  const doc = generateIncidentReport(event)
  doc.save(`incident-${event.rca_event_id}.pdf`)
}
