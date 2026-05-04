'use client'

import { useEffect, useState } from 'react'
import {
  Activity,
  RefreshCw,
  Radio,
  AlertTriangle,
  CheckCircle,
  Clock,
  Wifi,
  Zap,
  TrendingUp,
  MapPin,
  Bell
} from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import KpiCard from '@/components/KpiCard'
import { useWebSocket, RCAEvent } from '@/lib/websocket'
import { useNotifications } from '@/lib/notifications'
import { cn, formatNumber } from '@/lib/utils'
import Link from 'next/link'

export default function RealtimeDashboard() {
  const { events, isConnected } = useWebSocket('ws://localhost:8765')
  const { notifications, unreadCount, markAsRead } = useNotifications()
  const [stats, setStats] = useState({
    totalProcessed: 0,
    anomalies: 0,
    critical: 0,
    autoRemediated: 0
  })

  // Calculate stats from events
  useEffect(() => {
    if (events.length > 0) {
      const anomalies = events.filter(e => e.anomaly_severity !== 'low').length
      const critical = events.filter(e => ['critical', 'high'].includes(e.anomaly_severity)).length
      const autoRemediated = events.filter(e => e.remediation?.primary_action?.auto).length
      
      setStats({
        totalProcessed: events.length,
        anomalies,
        critical,
        autoRemediated
      })
    }
  }, [events])

  // Notifications are added by Header.tsx via the shared NotificationContext

  // Prepare chart data
  const severityData = [
    { name: 'Low', value: events.filter(e => e.anomaly_severity === 'low').length, color: '#10b981' },
    { name: 'Medium', value: events.filter(e => e.anomaly_severity === 'medium').length, color: '#f59e0b' },
    { name: 'High', value: events.filter(e => e.anomaly_severity === 'high').length, color: '#f43f5e' },
    { name: 'Critical', value: events.filter(e => e.anomaly_severity === 'critical').length, color: '#8b5cf6' }
  ]

  const recentEvents = events.slice(0, 10)

  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        {/* Connection Status */}
        <div className={cn(
          'px-4 py-2 text-xs font-medium flex items-center gap-2',
          isConnected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
        )}>
          <div className={cn('w-2 h-2 rounded-full', isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500')} />
          {isConnected ? 'Live Stream Connected' : 'Disconnected - Retrying...'}
          <span className="ml-auto">{events.length.toLocaleString()} events received</span>
        </div>

        <main className="flex-1 overflow-y-auto p-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <KpiCard
              title="Total Events"
              value={formatNumber(stats.totalProcessed)}
              icon={Activity}
              color="blue"
              change={events.length > 0 ? '+Live' : '0'}
            />
            <KpiCard
              title="Anomalies Detected"
              value={formatNumber(stats.anomalies)}
              icon={AlertTriangle}
              color="amber"
              change={`${((stats.anomalies / Math.max(stats.totalProcessed, 1)) * 100).toFixed(1)}%`}
            />
            <KpiCard
              title="Critical Alerts"
              value={formatNumber(stats.critical)}
              icon={Zap}
              color="rose"
              change={stats.critical > 0 ? 'Action Needed' : 'Clear'}
            />
            <KpiCard
              title="Auto-Remediated"
              value={formatNumber(stats.autoRemediated)}
              icon={CheckCircle}
              color="emerald"
              change="By AI"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Live Event Stream */}
            <div className="lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Radio className="w-5 h-5 text-accent-cyan" />
                  Live Event Stream
                </h2>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-navy-400">Real-time RCA feed from Detection Agent</span>
                  <RefreshCw className={cn('w-4 h-4 text-navy-400', isConnected && 'animate-spin')} />
                </div>
              </div>

              <div className="space-y-3 max-h-[500px] overflow-y-auto">
                {recentEvents.length === 0 ? (
                  <div className="glass rounded-xl p-8 text-center">
                    <Clock className="w-12 h-12 text-navy-400 mx-auto mb-3" />
                    <p className="text-navy-400">Waiting for events from Detection Agent...</p>
                    <p className="text-xs text-navy-500 mt-2">Start the Python agents: python agents/detection_agent.py --mode stream</p>
                  </div>
                ) : (
                  recentEvents.map((event) => (
                    <Link
                      key={event.rca_event_id}
                      href={`/incidents?id=${event.rca_event_id}`}
                      className="glass rounded-xl p-4 hover:border-accent-blue/50 transition-all block"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <span className="text-sm font-medium text-white">{event.rca_event_id}</span>
                            <span className={cn(
                              'px-2 py-0.5 rounded text-xs font-medium',
                              event.anomaly_severity === 'critical' ? 'bg-rose-500/20 text-rose-400' :
                              event.anomaly_severity === 'high' ? 'bg-amber-500/20 text-amber-400' :
                              event.anomaly_severity === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                              'bg-emerald-500/20 text-emerald-400'
                            )}>
                              {event.anomaly_severity.toUpperCase()}
                            </span>
                            {event.remediation?.primary_action?.auto && (
                              <span className="px-2 py-0.5 bg-accent-cyan/20 text-accent-cyan rounded text-xs">
                                Auto
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-navy-300 mb-1">
                            <span className="text-accent-blue">{event.cell_id}</span>
                            {' '}• {event.region} • {event.vendor}
                          </p>
                          <p className="text-xs text-navy-400">
                            {event.rca?.primary_cause || 'Analyzing...'}
                          </p>
                        </div>
                        <div className="text-right ml-4">
                          <p className="text-xs text-navy-500">
                            {new Date(event.timestamp).toLocaleTimeString()}
                          </p>
                          <p className="text-xs text-navy-500">
                            Score: {event.anomaly_score?.toFixed(3) || 'N/A'}
                          </p>
                        </div>
                      </div>
                    </Link>
                  ))
                )}
              </div>
            </div>

            {/* Side Panel */}
            <div className="space-y-6">
              {/* Severity Distribution */}
              <div className="glass rounded-xl p-5">
                <h3 className="text-sm font-semibold text-white mb-4">Severity Distribution</h3>
                <div className="space-y-3">
                  {severityData.map((item) => (
                    <div key={item.name} className="flex items-center gap-3">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                      <span className="text-sm text-navy-300 flex-1">{item.name}</span>
                      <span className="text-sm font-medium text-white">{item.value}</span>
                      <div className="w-20 h-2 bg-navy-700 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            backgroundColor: item.color,
                            width: `${Math.max((item.value / Math.max(events.length, 1)) * 100, 5)}%`
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Top Affected Cells */}
              <div className="glass rounded-xl p-5">
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <MapPin className="w-4 h-4" />
                  Top Affected Cells
                </h3>
                <div className="space-y-2">
                  {Object.entries(
                    events.reduce((acc, e) => {
                      acc[e.cell_id] = (acc[e.cell_id] || 0) + 1
                      return acc
                    }, {} as Record<string, number>)
                  )
                    .sort(([,a], [,b]) => b - a)
                    .slice(0, 5)
                    .map(([cellId, count]) => (
                      <div key={cellId} className="flex items-center justify-between text-sm">
                        <span className="text-navy-300">{cellId}</span>
                        <span className="text-white font-medium">{count} events</span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Notifications */}
              <div className="glass rounded-xl p-5">
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <Bell className="w-4 h-4" />
                  Notifications
                  {unreadCount > 0 && (
                    <span className="px-2 py-0.5 bg-rose-500 text-white text-xs rounded-full">
                      {unreadCount}
                    </span>
                  )}
                </h3>
                <div className="space-y-2 max-h-[200px] overflow-y-auto">
                  {notifications.slice(0, 5).map((notif) => (
                    <div
                      key={notif.id}
                      onClick={() => markAsRead(notif.id)}
                      className={cn(
                        'p-3 rounded-lg text-xs cursor-pointer transition-colors',
                        notif.read ? 'bg-navy-700/30' : 'bg-navy-700/50',
                        notif.type === 'error' ? 'border-l-2 border-rose-500' :
                        notif.type === 'warning' ? 'border-l-2 border-amber-500' :
                        'border-l-2 border-accent-blue'
                      )}
                    >
                      <p className="font-medium text-white mb-1">{notif.title}</p>
                      <p className="text-navy-400">{notif.message}</p>
                    </div>
                  ))}
                  {notifications.length === 0 && (
                    <p className="text-xs text-navy-500 text-center py-4">No notifications yet</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
