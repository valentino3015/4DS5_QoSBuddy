'use client'

import { useState } from 'react'
import {
  AlertTriangle,
  Download,
  Filter,
  Search,
  ChevronLeft,
  ChevronRight,
  FileText,
  Calendar,
  Activity,
  BrainCircuit,
  FileDown
} from 'lucide-react'
import { mockIncidents } from '@/lib/data'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { cn, formatDate, getSeverityColor } from '@/lib/utils'
import { jsPDF } from 'jspdf'

export default function IncidentsPage() {
  const [selectedIncident, setSelectedIncident] = useState<typeof mockIncidents[0] | null>(null)
  const [filterSeverity, setFilterSeverity] = useState<string>('all')
  const [searchTerm, setSearchTerm] = useState('')

  const filteredIncidents = mockIncidents.filter(incident => {
    if (filterSeverity !== 'all' && incident.severity !== filterSeverity) return false
    if (searchTerm && !incident.id.toLowerCase().includes(searchTerm.toLowerCase()) &&
        !incident.cellId.toLowerCase().includes(searchTerm.toLowerCase())) return false
    return true
  })

  const downloadReport = (incident: typeof mockIncidents[0]) => {
    const report = {
      incident_id: incident.id,
      timestamp: incident.timestamp,
      cell_id: incident.cellId,
      site_id: incident.siteId,
      region: incident.region,
      severity: incident.severity,
      anomaly_score: incident.anomalyScore,
      kpi_snapshot: incident.kpiSnapshot,
      root_cause_analysis: incident.rca,
      remediation: incident.remediation
    }
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${incident.id}_report.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const downloadPDF = (incident: typeof mockIncidents[0]) => {
    const doc = new jsPDF()
    
    // Header
    doc.setFontSize(20)
    doc.setTextColor(44, 62, 80)
    doc.text('QoSBuddy Incident Report', 20, 20)
    
    doc.setFontSize(12)
    doc.setTextColor(100, 100, 100)
    doc.text(`Generated: ${new Date().toLocaleString()}`, 20, 30)
    
    // Incident Info
    doc.setFontSize(14)
    doc.setTextColor(44, 62, 80)
    doc.text('Incident Details', 20, 45)
    
    doc.setFontSize(10)
    doc.setTextColor(0, 0, 0)
    const details = [
      `Incident ID: ${incident.id}`,
      `Cell ID: ${incident.cellId}`,
      `Site ID: ${incident.siteId}`,
      `Region: ${incident.region}`,
      `Severity: ${incident.severity.toUpperCase()}`,
      `Timestamp: ${formatDate(incident.timestamp)}`,
      `Anomaly Score: ${(incident.anomalyScore * 100).toFixed(1)}%`,
    ]
    let y = 55
    details.forEach(line => {
      doc.text(line, 20, y)
      y += 6
    })
    
    // Root Cause Analysis
    y += 10
    doc.setFontSize(14)
    doc.setTextColor(44, 62, 80)
    doc.text('Root Cause Analysis', 20, y)
    y += 8
    
    doc.setFontSize(10)
    doc.setTextColor(0, 0, 0)
    doc.text(`Predicted Cause: ${incident.rca.predictedCause}`, 20, y)
    y += 6
    doc.text(`Confidence: ${(incident.rca.confidence * 100).toFixed(0)}%`, 20, y)
    y += 6
    doc.text(`Similar Cases: ${incident.rca.similarCases}`, 20, y)
    y += 10
    
    // Top Features
    if (incident.rca.topFeatures.length > 0) {
      doc.setFontSize(12)
      doc.setTextColor(44, 62, 80)
      doc.text('Contributing Factors:', 20, y)
      y += 8
      
      doc.setFontSize(10)
      doc.setTextColor(0, 0, 0)
      incident.rca.topFeatures.forEach(feature => {
        doc.text(`• ${feature.feature}: ${(feature.importance * 100).toFixed(0)}%`, 20, y)
        y += 6
      })
    }
    
    // KPI Snapshot
    y += 10
    doc.setFontSize(14)
    doc.setTextColor(44, 62, 80)
    doc.text('KPI Snapshot', 20, y)
    y += 8
    
    doc.setFontSize(10)
    doc.setTextColor(0, 0, 0)
    const kpiLines = [
      `RSRP: ${incident.kpiSnapshot.rsrp} dBm`,
      `SINR: ${incident.kpiSnapshot.sinr} dB`,
      `Throughput DL: ${incident.kpiSnapshot.throughputDL} Mbps`,
      `Throughput UL: ${incident.kpiSnapshot.throughputUL} Mbps`,
      `Latency: ${incident.kpiSnapshot.latency} ms`,
      `Call Drop Rate: ${incident.kpiSnapshot.callDropRate}%`,
      `Active Users: ${incident.kpiSnapshot.activeUsers}`,
    ]
    kpiLines.forEach(line => {
      doc.text(line, 20, y)
      y += 6
    })
    
    // Remediation
    if (incident.remediation) {
      y += 10
      doc.setFontSize(14)
      doc.setTextColor(44, 62, 80)
      doc.text('Recommended Action', 20, y)
      y += 8
      
      doc.setFontSize(10)
      doc.setTextColor(0, 0, 0)
      doc.text(`Action: ${incident.remediation.action}`, 20, y)
      y += 6
      doc.text(`Priority: ${incident.remediation.priority}`, 20, y)
      y += 6
      doc.text(`ETA: ${incident.remediation.eta}h`, 20, y)
      y += 10
      
      doc.setFontSize(12)
      doc.setTextColor(44, 62, 80)
      doc.text('Steps:', 20, y)
      y += 8
      
      doc.setFontSize(10)
      doc.setTextColor(0, 0, 0)
      incident.remediation.steps.forEach((step, idx) => {
        const lines = doc.splitTextToSize(`${idx + 1}. ${step}`, 170)
        lines.forEach((line: string) => {
          doc.text(line, 20, y)
          y += 6
        })
      })
    }
    
    // Footer
    doc.setFontSize(8)
    doc.setTextColor(150, 150, 150)
    doc.text('Generated by QoSBuddy - Network Quality Management System', 20, 280)
    
    doc.save(`${incident.id}_report.pdf`)
  }

  const downloadCSV = () => {
    const headers = ['ID', 'Cell ID', 'Site ID', 'Region', 'Severity', 'Anomaly Score', 'Timestamp', 'Root Cause']
    const rows = filteredIncidents.map(i => [
      i.id, i.cellId, i.siteId, i.region, i.severity, i.anomalyScore, i.timestamp, i.rca.predictedCause
    ])
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `incidents_report_${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-hidden flex">
          {/* Incidents List */}
          <div className="flex-1 overflow-y-auto p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                  <AlertTriangle className="w-6 h-6 text-rose-400" />
                  Incidents
                </h1>
                <p className="text-navy-400 mt-1">View and manage network anomalies</p>
              </div>
              <button
                onClick={downloadCSV}
                className="flex items-center gap-2 px-4 py-2 bg-accent-blue hover:bg-accent-blue/80 rounded-lg text-white font-medium transition-colors"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </button>
            </div>

            {/* Filters */}
            <div className="flex items-center gap-4 mb-6">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-navy-400" />
                <input
                  type="text"
                  placeholder="Search incidents..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 bg-navy-800 border border-navy-500/50 rounded-lg text-sm text-white placeholder-navy-400 focus:outline-none focus:border-accent-blue"
                />
              </div>
              <select
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value)}
                className="px-4 py-2 bg-navy-800 border border-navy-500/50 rounded-lg text-sm text-white focus:outline-none focus:border-accent-blue"
              >
                <option value="all">All Severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>

            {/* Incidents Table */}
            <div className="glass rounded-xl overflow-hidden">
              <table className="w-full">
                <thead className="bg-navy-700/50">
                  <tr className="text-left text-xs text-navy-400">
                    <th className="px-4 py-3 font-medium">Incident ID</th>
                    <th className="px-4 py-3 font-medium">Cell</th>
                    <th className="px-4 py-3 font-medium">Severity</th>
                    <th className="px-4 py-3 font-medium">Anomaly Score</th>
                    <th className="px-4 py-3 font-medium">Root Cause</th>
                    <th className="px-4 py-3 font-medium">Timestamp</th>
                    <th className="px-4 py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {filteredIncidents.map((incident) => (
                    <tr
                      key={incident.id}
                      onClick={() => setSelectedIncident(incident)}
                      className={cn(
                        'border-b border-navy-500/20 cursor-pointer transition-colors',
                        selectedIncident?.id === incident.id
                          ? 'bg-accent-blue/10'
                          : 'hover:bg-navy-700/30'
                      )}
                    >
                      <td className="px-4 py-3">
                        <span className="font-medium text-white">{incident.id}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className={cn('w-2 h-2 rounded-full', getSeverityColor(incident.severity))} />
                          <span className="text-navy-300">{incident.cellId}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            'px-2 py-1 rounded-full text-xs font-medium',
                            incident.severity === 'critical'
                              ? 'bg-rose-500/20 text-rose-400'
                              : incident.severity === 'high'
                                ? 'bg-orange-500/20 text-orange-400'
                                : incident.severity === 'medium'
                                  ? 'bg-amber-500/20 text-amber-400'
                                  : 'bg-blue-500/20 text-blue-400'
                          )}
                        >
                          {incident.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-2 bg-navy-700 rounded-full overflow-hidden">
                            <div
                              className={cn(
                                'h-full rounded-full',
                                incident.anomalyScore > 0.8 ? 'bg-rose-500' : 'bg-amber-500'
                              )}
                              style={{ width: `${incident.anomalyScore * 100}%` }}
                            />
                          </div>
                          <span className="text-navy-300">{(incident.anomalyScore * 100).toFixed(0)}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-navy-300 max-w-xs truncate">
                        {incident.rca.predictedCause}
                      </td>
                      <td className="px-4 py-3 text-navy-400">
                        {formatDate(incident.timestamp)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              downloadPDF(incident)
                            }}
                            className="p-1.5 hover:bg-navy-700 rounded-lg text-rose-400 transition-colors"
                            title="Download PDF"
                          >
                            <FileDown className="w-4 h-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              downloadReport(incident)
                            }}
                            className="p-1.5 hover:bg-navy-700 rounded-lg text-accent-blue transition-colors"
                            title="Download JSON"
                          >
                            <Download className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between mt-4">
              <p className="text-sm text-navy-400">
                Showing {filteredIncidents.length} of {mockIncidents.length} incidents
              </p>
              <div className="flex items-center gap-2">
                <button className="p-2 hover:bg-navy-700 rounded-lg text-navy-400 hover:text-white transition-colors">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button className="px-3 py-1.5 bg-accent-blue text-white rounded-lg text-sm font-medium">
                  1
                </button>
                <button className="p-2 hover:bg-navy-700 rounded-lg text-navy-400 hover:text-white transition-colors">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Incident Detail Panel */}
          {selectedIncident && (
            <div className="w-96 bg-navy-800 border-l border-navy-500/30 overflow-y-auto">
              <div className="p-4 border-b border-navy-500/30">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-navy-400">Incident ID</span>
                  <button
                    onClick={() => setSelectedIncident(null)}
                    className="text-navy-400 hover:text-white"
                  >
                    ×
                  </button>
                </div>
                <h2 className="text-lg font-bold text-white">{selectedIncident.id}</h2>
                <div className="flex items-center gap-2 mt-2">
                  <span
                    className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium',
                      selectedIncident.severity === 'critical'
                        ? 'bg-rose-500/20 text-rose-400'
                        : selectedIncident.severity === 'high'
                          ? 'bg-orange-500/20 text-orange-400'
                          : selectedIncident.severity === 'medium'
                            ? 'bg-amber-500/20 text-amber-400'
                            : 'bg-blue-500/20 text-blue-400'
                    )}
                  >
                    {selectedIncident.severity.toUpperCase()}
                  </span>
                  <span className="text-xs text-navy-400">
                    {formatDate(selectedIncident.timestamp)}
                  </span>
                </div>
              </div>

              <div className="p-4 space-y-4">
                {/* Location */}
                <div className="p-3 bg-navy-700/50 rounded-lg">
                  <h3 className="text-sm font-medium text-white mb-2 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-accent-blue" />
                    Location
                  </h3>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <p className="text-navy-400">Cell ID</p>
                      <p className="text-white">{selectedIncident.cellId}</p>
                    </div>
                    <div>
                      <p className="text-navy-400">Site ID</p>
                      <p className="text-white">{selectedIncident.siteId}</p>
                    </div>
                    <div>
                      <p className="text-navy-400">Region</p>
                      <p className="text-white">{selectedIncident.region}</p>
                    </div>
                  </div>
                </div>

                {/* RCA */}
                <div className="p-3 bg-navy-700/50 rounded-lg">
                  <h3 className="text-sm font-medium text-white mb-2 flex items-center gap-2">
                    <BrainCircuit className="w-4 h-4 text-accent-purple" />
                    Root Cause Analysis
                  </h3>
                  <p className="text-sm text-navy-300 mb-2">{selectedIncident.rca.predictedCause}</p>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-navy-400">Confidence:</span>
                    <span className="text-white font-medium">{(selectedIncident.rca.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="mt-2">
                    <p className="text-xs text-navy-400 mb-1">Top Contributing Features:</p>
                    {selectedIncident.rca.topFeatures.map((feature, idx) => (
                      <div key={idx} className="flex items-center justify-between text-xs py-1">
                        <span className="text-navy-300">{feature.feature}</span>
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-navy-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-accent-blue rounded-full"
                              style={{ width: `${feature.importance * 100}%` }}
                            />
                          </div>
                          <span className="text-navy-400 w-8">{(feature.importance * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* KPI Snapshot */}
                <div className="p-3 bg-navy-700/50 rounded-lg">
                  <h3 className="text-sm font-medium text-white mb-2">KPI Snapshot</h3>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2 bg-navy-800/50 rounded">
                      <p className="text-navy-400">RSRP</p>
                      <p className={cn(
                        'font-medium',
                        selectedIncident.kpiSnapshot.rsrp > -90 ? 'text-emerald-400' :
                        selectedIncident.kpiSnapshot.rsrp > -100 ? 'text-amber-400' : 'text-rose-400'
                      )}>
                        {selectedIncident.kpiSnapshot.rsrp} dBm
                      </p>
                    </div>
                    <div className="p-2 bg-navy-800/50 rounded">
                      <p className="text-navy-400">SINR</p>
                      <p className={cn(
                        'font-medium',
                        selectedIncident.kpiSnapshot.sinr > 15 ? 'text-emerald-400' :
                        selectedIncident.kpiSnapshot.sinr > 5 ? 'text-amber-400' : 'text-rose-400'
                      )}>
                        {selectedIncident.kpiSnapshot.sinr} dB
                      </p>
                    </div>
                    <div className="p-2 bg-navy-800/50 rounded">
                      <p className="text-navy-400">DL Throughput</p>
                      <p className="text-white font-medium">{selectedIncident.kpiSnapshot.throughputDL} Mbps</p>
                    </div>
                    <div className="p-2 bg-navy-800/50 rounded">
                      <p className="text-navy-400">Latency</p>
                      <p className={cn(
                        'font-medium',
                        selectedIncident.kpiSnapshot.latency < 30 ? 'text-emerald-400' :
                        selectedIncident.kpiSnapshot.latency < 60 ? 'text-amber-400' : 'text-rose-400'
                      )}>
                        {selectedIncident.kpiSnapshot.latency} ms
                      </p>
                    </div>
                    <div className="p-2 bg-navy-800/50 rounded">
                      <p className="text-navy-400">Call Drop Rate</p>
                      <p className={cn(
                        'font-medium',
                        selectedIncident.kpiSnapshot.callDropRate < 2 ? 'text-emerald-400' :
                        selectedIncident.kpiSnapshot.callDropRate < 5 ? 'text-amber-400' : 'text-rose-400'
                      )}>
                        {selectedIncident.kpiSnapshot.callDropRate}%
                      </p>
                    </div>
                    <div className="p-2 bg-navy-800/50 rounded">
                      <p className="text-navy-400">Active Users</p>
                      <p className="text-white font-medium">{selectedIncident.kpiSnapshot.activeUsers}</p>
                    </div>
                  </div>
                </div>

                {/* Remediation */}
                {selectedIncident.remediation && (
                  <div className="p-3 bg-navy-700/50 rounded-lg">
                    <h3 className="text-sm font-medium text-white mb-2 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-accent-cyan" />
                      Recommended Action
                    </h3>
                    <p className="text-sm text-white font-medium mb-2">
                      {selectedIncident.remediation.action}
                    </p>
                    <div className="flex items-center gap-4 text-xs text-navy-400 mb-3">
                      <span>Priority: <span className="text-white">{selectedIncident.remediation.priority}</span></span>
                      <span>ETA: <span className="text-white">{selectedIncident.remediation.eta}h</span></span>
                    </div>
                    <ol className="text-xs text-navy-300 space-y-1 list-decimal list-inside">
                      {selectedIncident.remediation.steps.map((step, idx) => (
                        <li key={idx}>{step}</li>
                      ))}
                    </ol>
                  </div>
                )}

                {/* Download Buttons */}
                <div className="flex gap-2">
                  <button
                    onClick={() => downloadPDF(selectedIncident)}
                    className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-600/80 rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2"
                  >
                    <FileDown className="w-4 h-4" />
                    Download PDF
                  </button>
                  <button
                    onClick={() => downloadReport(selectedIncident)}
                    className="flex-1 py-2.5 bg-accent-blue hover:bg-accent-blue/80 rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2"
                  >
                    <Download className="w-4 h-4" />
                    Download JSON
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
