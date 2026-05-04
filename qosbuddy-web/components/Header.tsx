'use client'

import { useState, useEffect, useRef } from 'react'
import { Bell, Search, User, X, AlertTriangle, CheckCircle, Info } from 'lucide-react'
import { useWebSocket } from '@/lib/websocket'
import { useNotifications } from '@/lib/notifications'
import { cn } from '@/lib/utils'
import Link from 'next/link'

interface UserData {
  id: number
  name: string
  email: string
  role: string
}

export default function Header() {
  const [user, setUser] = useState<UserData | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNotifications, setShowNotifications] = useState(false)
  const { events } = useWebSocket('ws://localhost:8765')
  const { notifications, unreadCount, addNotification, markAsRead, markAllAsRead } = useNotifications()
  const processedEvents = useRef<Set<string>>(new Set())

  // Fetch current user
  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await fetch('/api/auth/me')
        if (response.ok) {
          const userData = await response.json()
          setUser(userData)
        }
      } catch (error) {
        console.error('Failed to fetch user:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchUser()
  }, [])

  // Add notifications for critical/high events (deduped by event id)
  useEffect(() => {
    const latestEvent = events[0]
    if (latestEvent && ['critical', 'high'].includes(latestEvent.anomaly_severity)) {
      if (!processedEvents.current.has(latestEvent.rca_event_id)) {
        processedEvents.current.add(latestEvent.rca_event_id)
        addNotification({
          title: `Critical Alert: ${latestEvent.cell_id}`,
          message: latestEvent.rca?.primary_cause || 'Anomaly detected',
          type: 'error',
          link: `/incidents?id=${latestEvent.rca_event_id}`
        })
      }
    }
  }, [events, addNotification])

  return (
    <header className="h-16 bg-navy-800/80 backdrop-blur-md border-b border-navy-500/30 flex items-center justify-between px-6 sticky top-0 z-40">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-navy-400" />
        <input
          type="text"
          placeholder="Search cells, incidents, or sites..."
          className="w-80 pl-10 pr-4 py-2 bg-navy-700 border border-navy-500/50 rounded-lg text-sm text-white placeholder-navy-400 focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue transition-all"
        />
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4 relative">
        {/* Notifications */}
        <div className="relative">
          <button 
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-lg hover:bg-navy-700 text-navy-400 hover:text-white transition-colors"
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center animate-pulse">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>

          {/* Notification Dropdown */}
          {showNotifications && (
            <div className="absolute right-0 top-full mt-2 w-96 bg-navy-800 border border-navy-500/30 rounded-xl shadow-2xl z-50 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-navy-500/30">
                <h3 className="font-semibold text-white">Notifications</h3>
                <div className="flex items-center gap-2">
                  {unreadCount > 0 && (
                    <button
                      onClick={markAllAsRead}
                      className="text-xs text-accent-blue hover:text-accent-blue/80"
                    >
                      Mark all read
                    </button>
                  )}
                  <button
                    onClick={() => setShowNotifications(false)}
                    className="p-1 hover:bg-navy-700 rounded"
                  >
                    <X className="w-4 h-4 text-navy-400" />
                  </button>
                </div>
              </div>

              <div className="max-h-80 overflow-y-auto">
                {notifications.length === 0 ? (
                  <p className="px-4 py-8 text-center text-navy-400 text-sm">
                    No notifications yet
                  </p>
                ) : (
                  notifications.map((notif) => (
                    <div
                      key={notif.id}
                      onClick={() => {
                        markAsRead(notif.id)
                        if (notif.link) window.location.href = notif.link
                      }}
                      className={cn(
                        'px-4 py-3 border-b border-navy-500/20 cursor-pointer hover:bg-navy-700/50 transition-colors',
                        !notif.read && 'bg-navy-700/30'
                      )}
                    >
                      <div className="flex items-start gap-3">
                        {notif.type === 'error' && <AlertTriangle className="w-4 h-4 text-rose-400 mt-0.5" />}
                        {notif.type === 'warning' && <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5" />}
                        {notif.type === 'success' && <CheckCircle className="w-4 h-4 text-emerald-400 mt-0.5" />}
                        {notif.type === 'info' && <Info className="w-4 h-4 text-blue-400 mt-0.5" />}
                        <div className="flex-1">
                          <p className="text-sm font-medium text-white">{notif.title}</p>
                          <p className="text-xs text-navy-400 mt-0.5">{notif.message}</p>
                          <p className="text-xs text-navy-500 mt-1">
                            {notif.timestamp.toLocaleTimeString()}
                          </p>
                        </div>
                        {!notif.read && (
                          <div className="w-2 h-2 bg-accent-blue rounded-full mt-1" />
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* User */}
        <div className="flex items-center gap-3 pl-4 border-l border-navy-500/30">
          <div className="text-right hidden sm:block">
            {loading ? (
              <p className="text-sm font-medium text-white">Loading...</p>
            ) : user ? (
              <>
                <p className="text-sm font-medium text-white">{user.name}</p>
                <p className="text-xs text-navy-400 capitalize">{user.role}</p>
              </>
            ) : (
              <p className="text-sm font-medium text-white">Guest</p>
            )}
          </div>
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-accent-purple to-accent-blue flex items-center justify-center">
            <User className="w-5 h-5 text-white" />
          </div>
        </div>
      </div>
    </header>
  )
}
