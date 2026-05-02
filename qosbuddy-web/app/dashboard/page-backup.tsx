'use client'

import { useState } from 'react'
import {
  Activity,
  Wifi,
  AlertTriangle,
  Zap,
  Signal,
  Clock,
  Users,
  Download,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Server,
  Cpu
} from 'lucide-react'
import { mockIncidents, mockCells } from '@/lib/data'
import KpiCard from '@/components/KpiCard'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { cn, formatDate, getSeverityColor } from '@/lib/utils'

export default function DashboardPage() {
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = () => {
    setRefreshing(true)
    setTimeout(() => setRefreshing(false), 1000)
  }

  const stats = {
    totalCells: mockCells.length,
    activeCells: mockCells.filter(c => c.status === 'normal').length,
    warningCells: mockCells.filter(c => c.status === 'warning').length,
    criticalCells: mockCells.filter(c => c.status === 'critical').length,
    avgThroughput: Math.round(mockCells.reduce((acc, c) => acc + c.throughput, 0) / mockCells.length),
    avgLatency: Math.round(mockCells.reduce((acc, c) => acc + c.latency, 0) / mockCells.length),
  }

  const recentIncidents = mockIncidents.slice(0, 5)

  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {/* Page header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white">Dashboard</h1>
              <p className="text-navy-400 mt-1">Real-time network performance overview</p>
            </div>
            <button
              onClick={handleRefresh}
              className={cn(
                'flex items-center gap-2 px-4 py-2 bg-navy-700 hover:bg-navy-600 rounded-lg text-sm font-medium transition-all',
                refreshing && 'animate-pulse'
              )}
            >
              <RefreshCw className={cn('w-4 h-4', refreshing && 'animate-spin')} />
              Refresh
            </button>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <KpiCard
              title="Total Cells"
              value={stats.totalCells}
              change={2.5}
              icon={Server}
              color="blue"
              subtitle={`${stats.activeCells} active, ${stats.criticalCells} critical`}
            />
            <KpiCard
              title="Avg Throughput"
              value={stats.avgThroughput}
              unit="Mbps"
              change={-3.2}
              icon={Wifi}
              color="emerald"
            />
            <KpiCard
              title="Avg Latency"
              value={stats.avgLatency}
              unit="ms"
              change={5.8}
              icon={Clock}
              color="amber"
            />
            <KpiCard
              title="Active Users"
              value="4,280"
              change={12.3}
              icon={Users}
              color="purple"
              subtitle="Across all cells"
            />
          </div>

          {/* Secondary KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <KpiCard
              title="Signal Quality"
              value="87%"
              change={1.5}
              icon={Signal}
              color="cyan"
            />
            <KpiCard
              title="Power Usage"
              value="12.4"
              unit="kW"
              change={-2.1}
              icon={Zap}
              color="amber"
            />
            <KpiCard
              title="CPU Utilization"
              value="42%"
              change={-5.2}
              icon={Cpu}
              color="purple"
            />
          </div>

          {/* Main content grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Network Health Chart */}
            <div className="lg:col-span-2 glass rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white">Network Health Trends</h3>
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 text-xs text-emerald-400">
                    <div className="w-2 h-2 rounded-full bg-emerald-500" />
                    Healthy
                  </span>
                  <span className="flex items-center gap-1 text-xs text-amber-400">
                    <div className="w-2 h-2 rounded-full bg-amber-500" />
                    Warning
                  </span>
                  <span className="flex items-center gap-1 text-xs text-rose-400">
                    <div className="w-2 h-2 rounded-full bg-rose-500" />
                    Critical
                  </span>
                </div>
              </div>
              <div className="h-64 flex items-end justify-between gap-2 px-2">
                {Array.from({ length: 24 }).map((_, i) => {
                  const healthy = Math.random() * 60 + 20
                  const warning = Math.random() * 15
                  const critical = Math.random() * 5
                  return (
                    <div key={i} className="flex-1 flex flex-col gap-0.5">
                      <div
                        className="w-full bg-rose-500/80 rounded-t"
                        style={{ height: `${critical}%` }}
                      />
                      <div
                        className="w-full bg-amber-500/80 rounded-t"
                        style={{ height: `${warning}%` }}
                      />
                      <div
                        className="w-full bg-emerald-500/80 rounded-t"
                        style={{ height: `${healthy}%` }}
                      />
                    </div>
                  )
                })}
              </div>
              <div className="flex justify-between mt-2 text-xs text-navy-400">
                <span>00:00</span>
                <span>06:00</span>
                <span>12:00</span>
                <span>18:00</span>
                <span>23:59</span>
              </div>
            </div>

            {/* Cell Status */}
            <div className="glass rounded-xl p-5">
              <h3 className="text-lg font-semibold text-white mb-4">Cell Status Distribution</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-emerald-500" />
                    <span className="text-navy-300">Normal</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-32 h-2 bg-navy-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full"
                        style={{ width: `${(stats.activeCells / stats.totalCells) * 100}%` }}
                      />
                    </div>
                    <span className="text-white font-medium w-6">{stats.activeCells}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-amber-500" />
                    <span className="text-navy-300">Warning</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-32 h-2 bg-navy-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-amber-500 rounded-full"
                        style={{ width: `${(stats.warningCells / stats.totalCells) * 100}%` }}
                      />
                    </div>
                    <span className="text-white font-medium w-6">{stats.warningCells}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-rose-500" />
                    <span className="text-navy-300">Critical</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-32 h-2 bg-navy-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-rose-500 rounded-full"
                        style={{ width: `${(stats.criticalCells / stats.totalCells) * 100}%` }}
                      />
                    </div>
                    <span className="text-white font-medium w-6">{stats.criticalCells}</span>
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-navy-500/30">
                <h4 className="text-sm font-medium text-navy-400 mb-3">Critical Cells</h4>
                <div className="space-y-2">
                  {mockCells
                    .filter(c => c.status === 'critical')
                    .map(cell => (
                      <div
                        key={cell.id}
                        className="flex items-center justify-between p-2 bg-rose-500/10 rounded-lg border border-rose-500/20"
                      >
                        <span className="text-sm text-white">{cell.id}</span>
                        <div className="flex items-center gap-2">
                          <Activity className="w-4 h-4 text-rose-400" />
                          <span className="text-xs text-rose-400">{cell.rsrp} dBm</span>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </div>

            {/* Recent Incidents */}
            <div className="lg:col-span-2 glass rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-rose-400" />
                  Recent Incidents
                </h3>
                <button className="text-sm text-accent-blue hover:text-accent-cyan transition-colors">
                  View all
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-xs text-navy-400 border-b border-navy-500/30">
                      <th className="pb-3 font-medium">ID</th>
                      <th className="pb-3 font-medium">Cell</th>
                      <th className="pb-3 font-medium">Severity</th>
                      <th className="pb-3 font-medium">Anomaly Score</th>
                      <th className="pb-3 font-medium">Root Cause</th>
                      <th className="pb-3 font-medium">Time</th>
                      <th className="pb-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="text-sm">
                    {recentIncidents.map((incident) => (
                      <tr
                        key={incident.id}
                        className="border-b border-navy-500/20 last:border-0 hover:bg-navy-700/30 transition-colors"
                      >
                        <td className="py-3 text-white font-medium">{incident.id}</td>
                        <td className="py-3">
                          <div className="flex items-center gap-2">
                            <div className={cn('w-2 h-2 rounded-full', getSeverityColor(incident.severity))} />
                            <span className="text-navy-300">{incident.cellId}</span>
                          </div>
                        </td>
                        <td className="py-3">
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
                        <td className="py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-20 h-2 bg-navy-700 rounded-full overflow-hidden">
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
                        <td className="py-3 text-navy-300 max-w-xs truncate">
                          {incident.rca.predictedCause}
                        </td>
                        <td className="py-3 text-navy-400">
                          {formatDate(incident.timestamp)}
                        </td>
                        <td className="py-3">
                          <button className="flex items-center gap-1 text-accent-blue hover:text-accent-cyan transition-colors text-xs">
                            <Download className="w-4 h-4" />
                            Report
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Quick Stats */}
            <div className="glass rounded-xl p-5">
              <h3 className="text-lg font-semibold text-white mb-4">24h Summary</h3>
              <div className="space-y-4">
                <div className="p-3 bg-navy-700/50 rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-navy-400">Incidents Detected</span>
                    <TrendingUp className="w-4 h-4 text-rose-400" />
                  </div>
                  <span className="text-2xl font-bold text-white">23</span>
                  <span className="text-xs text-rose-400 ml-2">+4 vs yesterday</span>
                </div>
                <div className="p-3 bg-navy-700/50 rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-navy-400">Avg Resolution Time</span>
                    <TrendingDown className="w-4 h-4 text-emerald-400" />
                  </div>
                  <span className="text-2xl font-bold text-white">2.4h</span>
                  <span className="text-xs text-emerald-400 ml-2">-0.8h vs yesterday</span>
                </div>
                <div className="p-3 bg-navy-700/50 rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-navy-400">Auto-Remediation</span>
                    <TrendingUp className="w-4 h-4 text-emerald-400" />
                  </div>
                  <span className="text-2xl font-bold text-white">68%</span>
                  <span className="text-xs text-emerald-400 ml-2">+12% vs yesterday</span>
                </div>
                <div className="p-3 bg-navy-700/50 rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-navy-400">MTTR</span>
                    <TrendingDown className="w-4 h-4 text-emerald-400" />
                  </div>
                  <span className="text-2xl font-bold text-white">45m</span>
                  <span className="text-xs text-emerald-400 ml-2">-15m vs yesterday</span>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
