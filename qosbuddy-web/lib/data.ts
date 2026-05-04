export interface Cell {
  id: string
  siteId: string
  region: string
  vendor: string
  nrBand: string
  networkSlice: string
  lat: number
  lng: number
  status: 'normal' | 'warning' | 'critical'
  rsrp: number
  sinr: number
  throughput: number
  latency: number
  neighbors: string[]
}

export interface Incident {
  id: string
  cellId: string
  siteId: string
  region: string
  timestamp: string
  severity: 'normal' | 'low' | 'medium' | 'high' | 'critical'
  anomalyScore: number
  kpiSnapshot: {
    rsrp: number
    sinr: number
    prbUtilDL: number
    prbUtilUL: number
    cqi: number
    blerDL: number
    blerUL: number
    throughputDL: number
    throughputUL: number
    latency: number
    callDropRate: number
    hoSuccessRate: number
    mos: number
    mimoRank: number
    activeUsers: number
  }
  rca: {
    predictedCause: string
    confidence: number
    topFeatures: { feature: string; importance: number }[]
    similarCases: number
  }
  remediation?: {
    action: string
    steps: string[]
    priority: string
    effort: string
    eta: number
    auto: boolean
  }
}

export interface User {
  id: string
  name: string
  email: string
  role: 'admin' | 'engineer' | 'viewer'
  avatar?: string
  notifications: boolean
  createdAt: string
}
