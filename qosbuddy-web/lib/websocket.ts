import { useEffect, useRef, useState, useCallback } from 'react'

export interface RCAEvent {
  rca_event_id: string
  agent: string
  phase: string
  processed_at: string
  source_event_id: string
  timestamp: string
  cell_id: string
  region: string
  vendor: string
  nr_band: string
  network_slice: string
  anomaly_severity: 'low' | 'medium' | 'high' | 'critical'
  anomaly_score: number
  kpi_snapshot: Record<string, number>
  rule_engine: {
    triggered?: boolean
    reasons?: string[]
  }
  rca: {
    primary_cause?: string
    confidence?: number
    explanation?: string
    shap_summary?: string
    similar_cases?: Array<{
      cell_id: string
      distance: number
      outcome: string
    }>
  }
  remediation: {
    cause: string
    primary_action: {
      action: string
      steps: string[]
      priority: string
      effort: string
      eta_hours: number
      auto: boolean
    }
    summary: string
    impact: string
  }
}

interface WebSocketMessage {
  type: 'snapshot' | 'event'
  data?: RCAEvent
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any
}

export function useWebSocket(url: string = 'ws://localhost:8765') {
  const [events, setEvents] = useState<RCAEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url)
      
      ws.onopen = () => {
        setIsConnected(true)
        setError(null)
      }

      ws.onmessage = (message) => {
        try {
          const data: WebSocketMessage = JSON.parse(message.data)
          
          if (data.type === 'snapshot') {
            // Remediation agent sends snapshot as { type: 'snapshot', events: [...], stats, ... }
            const snapshotData = Array.isArray(data.events) ? data.events : []
            // Reverse so newest events come first (agent stores oldest-first)
            setEvents([...snapshotData].reverse() as RCAEvent[])
          } else if (data.type === 'event') {
            // New live event - add to beginning
            const newEvent = data.data as RCAEvent
            setEvents(prev => [newEvent, ...prev].slice(0, 2000))
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      ws.onclose = () => {
        setIsConnected(false)
        // Auto-reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          connect()
        }, 3000)
      }

      ws.onerror = () => {
        setError('WebSocket connection failed')
        setIsConnected(false)
      }

      wsRef.current = ws
    } catch (e) {
      setError('Failed to create WebSocket connection')
    }
  }, [url])

  useEffect(() => {
    connect()
    
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      wsRef.current?.close()
    }
  }, [connect])

  return { events, isConnected, error }
}
