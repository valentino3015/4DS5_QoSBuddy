'use client'

import { useState } from 'react'
import {
  Wrench,
  BrainCircuit,
  Clock,
  AlertTriangle,
  RotateCcw,
  FileText,
  ChevronRight,
  Bot,
  CheckCircle,
  Zap,
  Play,
  X
} from 'lucide-react'
import { mockIncidents } from '@/lib/data'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { cn, formatDate } from '@/lib/utils'

export default function RemediationPage() {
  const [autoRemediate, setAutoRemediate] = useState(true)

  const remediationQueue = mockIncidents.filter(i => i.remediation).slice(0, 3)

  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                <Wrench className="w-6 h-6 text-accent-cyan" />
                AI Remediation
              </h1>
              <p className="text-navy-400 mt-1">LLM-powered automated network healing</p>
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-navy-400 cursor-pointer hover:text-navy-300">
                <input
                  type="checkbox"
                  checked={autoRemediate}
                  onChange={(e) => setAutoRemediate(e.target.checked)}
                  className="w-3 h-3 rounded border-navy-500"
                />
                Auto-remediate
              </label>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Stats */}
            <div className="lg:col-span-3 grid grid-cols-4 gap-4">
              {[
                { label: 'Pending', value: '3', color: 'text-amber-400', icon: Clock },
                { label: 'In Progress', value: '1', color: 'text-accent-blue', icon: Play },
                { label: 'Completed (24h)', value: '12', color: 'text-emerald-400', icon: CheckCircle },
                { label: 'Auto-Success Rate', value: '68%', color: 'text-accent-cyan', icon: Zap },
              ].map((stat, idx) => (
                <div key={idx} className="glass rounded-xl p-4 flex items-center gap-3">
                  <div className="p-2 bg-navy-700/50 rounded-lg">
                    <stat.icon className={cn('w-5 h-5', stat.color)} />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-white">{stat.value}</p>
                    <p className="text-xs text-navy-400">{stat.label}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Remediation Queue */}
            <div className="lg:col-span-2 space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                Remediation Queue
              </h2>
              {remediationQueue.map((incident) => (
                <div key={incident.id} className="glass rounded-xl p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-white">{incident.id}</span>
                        <span className="px-2 py-0.5 bg-rose-500/20 text-rose-400 rounded text-xs">
                          {incident.severity}
                        </span>
                      </div>
                      <p className="text-sm text-navy-400">{incident.cellId} • {formatDate(incident.timestamp)}</p>
                    </div>
                  </div>

                  <div className="p-3 bg-navy-700/50 rounded-lg mb-4">
                    <div className="flex items-center gap-2 mb-2">
                      <BrainCircuit className="w-4 h-4 text-accent-purple" />
                      <span className="text-sm font-medium text-white">AI Recommendation</span>
                    </div>
                    <p className="text-sm text-navy-300 mb-2">{incident.remediation?.action}</p>
                    <div className="flex items-center gap-4 text-xs text-navy-400">
                      <span>Priority: <span className="text-white">{incident.remediation?.priority}</span></span>
                      <span>ETA: <span className="text-white">{incident.remediation?.eta}h</span></span>
                      <span>Effort: <span className="text-white">{incident.remediation?.effort}</span></span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Bot className="w-4 h-4 text-accent-cyan" />
                      <span className="text-xs text-accent-cyan">AI-Powered</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {incident.remediation?.steps.slice(0, 2).map((step, idx) => (
                        <span key={idx} className="text-xs text-navy-400 flex items-center gap-1">
                          {idx > 0 && <ChevronRight className="w-3 h-3" />}
                          {step}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Side Panel */}
            <div className="space-y-4">
              <div className="glass rounded-xl p-5">
                <h3 className="text-sm font-semibold text-white mb-4">Recent Actions</h3>
                <div className="space-y-3">
                  {[
                    { action: 'Power boost applied', cell: 'gNB_002_C1', time: '5 min ago', status: 'success' },
                    { action: 'Load balancing enabled', cell: 'gNB_001_C3', time: '12 min ago', status: 'success' },
                    { action: 'Antenna adjustment', cell: 'gNB_005_C2', time: '28 min ago', status: 'pending' },
                  ].map((item, idx) => (
                    <div key={idx} className="flex items-start gap-3">
                      <div className={cn(
                        'w-2 h-2 rounded-full mt-1.5',
                        item.status === 'success' ? 'bg-emerald-500' : 'bg-amber-500'
                      )} />
                      <div>
                        <p className="text-sm text-white">{item.action}</p>
                        <p className="text-xs text-navy-400">{item.cell} • {item.time}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
