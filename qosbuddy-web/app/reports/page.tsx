'use client'

import { useState } from 'react'
import {
  FileText,
  Download,
  Calendar,
  TrendingUp,
  BarChart3,
  PieChart,
  Activity,
  ChevronDown
} from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { cn } from '@/lib/utils'

export default function ReportsPage() {
  const [dateRange, setDateRange] = useState('7d')

  const reportTypes = [
    { id: 'performance', name: 'Performance Report', icon: TrendingUp, desc: 'KPI trends and throughput analysis' },
    { id: 'incidents', name: 'Incident Summary', icon: Activity, desc: 'Anomalies and root cause analysis' },
    { id: 'coverage', name: 'Coverage Map', icon: BarChart3, desc: 'Signal quality and cell distribution' },
    { id: 'remediation', name: 'Remediation Log', icon: FileText, desc: 'AI actions and success rates' },
  ]

  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                <FileText className="w-6 h-6 text-accent-cyan" />
                Reports
              </h1>
              <p className="text-navy-400 mt-1">Generate and download network reports</p>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={dateRange}
                onChange={(e) => setDateRange(e.target.value)}
                className="px-4 py-2 bg-navy-800 border border-navy-500/50 rounded-lg text-sm text-white focus:outline-none focus:border-accent-blue"
              >
                <option value="24h">Last 24 hours</option>
                <option value="7d">Last 7 days</option>
                <option value="30d">Last 30 days</option>
                <option value="90d">Last 90 days</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {reportTypes.map((report) => (
              <div key={report.id} className="glass rounded-xl p-6 hover:border-accent-blue/50 transition-colors">
                <div className="flex items-start justify-between mb-4">
                  <div className="p-3 bg-navy-700/50 rounded-lg">
                    <report.icon className="w-6 h-6 text-accent-blue" />
                  </div>
                  <button className="p-2 hover:bg-navy-700 rounded-lg text-navy-400 hover:text-white transition-colors">
                    <Download className="w-5 h-5" />
                  </button>
                </div>
                <h3 className="text-lg font-semibold text-white mb-1">{report.name}</h3>
                <p className="text-sm text-navy-400 mb-4">{report.desc}</p>
                <div className="flex items-center gap-4">
                  <button className="flex-1 py-2 bg-accent-blue hover:bg-accent-blue/80 rounded-lg text-white text-sm font-medium transition-colors">
                    Generate PDF
                  </button>
                  <button className="flex-1 py-2 bg-navy-700 hover:bg-navy-600 rounded-lg text-white text-sm font-medium transition-colors">
                    Export CSV
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Scheduled Reports */}
          <div className="mt-8">
            <h2 className="text-lg font-semibold text-white mb-4">Scheduled Reports</h2>
            <div className="glass rounded-xl overflow-hidden">
              <table className="w-full">
                <thead className="bg-navy-700/50">
                  <tr className="text-left text-xs text-navy-400">
                    <th className="px-6 py-3 font-medium">Report Name</th>
                    <th className="px-6 py-3 font-medium">Frequency</th>
                    <th className="px-6 py-3 font-medium">Next Run</th>
                    <th className="px-6 py-3 font-medium">Recipients</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {[
                    { name: 'Weekly Performance', freq: 'Weekly', next: 'Mon, 8:00 AM', recipients: 'All Engineers', status: 'Active' },
                    { name: 'Daily Incident Digest', freq: 'Daily', next: 'Tomorrow, 6:00 AM', recipients: 'Admin Only', status: 'Active' },
                    { name: 'Monthly Executive', freq: 'Monthly', next: '1st of month', recipients: 'Management', status: 'Paused' },
                  ].map((row, idx) => (
                    <tr key={idx} className="border-b border-navy-500/20 hover:bg-navy-700/30 transition-colors">
                      <td className="px-6 py-3 text-white">{row.name}</td>
                      <td className="px-6 py-3 text-navy-300">{row.freq}</td>
                      <td className="px-6 py-3 text-navy-300">{row.next}</td>
                      <td className="px-6 py-3 text-navy-300">{row.recipients}</td>
                      <td className="px-6 py-3">
                        <span className={cn(
                          'px-2 py-0.5 rounded text-xs font-medium',
                          row.status === 'Active' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'
                        )}>
                          {row.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
