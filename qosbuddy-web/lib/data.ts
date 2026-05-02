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

export const mockCells: Cell[] = [
  { id: 'gNB_001_C1', siteId: 'SITE_001', region: 'North', vendor: 'Nokia', nrBand: 'n78', networkSlice: 'eMBB', lat: 48.8566, lng: 2.3522, status: 'normal', rsrp: -85, sinr: 15, throughput: 450, latency: 25, neighbors: ['gNB_001_C2', 'gNB_002_C1', 'gNB_003_C1'] },
  { id: 'gNB_001_C2', siteId: 'SITE_001', region: 'North', vendor: 'Nokia', nrBand: 'n78', networkSlice: 'eMBB', lat: 48.8566, lng: 2.3622, status: 'normal', rsrp: -82, sinr: 18, throughput: 520, latency: 22, neighbors: ['gNB_001_C1', 'gNB_002_C2'] },
  { id: 'gNB_001_C3', siteId: 'SITE_001', region: 'North', vendor: 'Nokia', nrBand: 'n78', networkSlice: 'URLLC', lat: 48.8666, lng: 2.3522, status: 'warning', rsrp: -92, sinr: 8, throughput: 280, latency: 45, neighbors: ['gNB_001_C1', 'gNB_004_C1'] },
  { id: 'gNB_002_C1', siteId: 'SITE_002', region: 'North', vendor: 'Ericsson', nrBand: 'n77', networkSlice: 'eMBB', lat: 48.8766, lng: 2.3722, status: 'critical', rsrp: -105, sinr: 2, throughput: 120, latency: 85, neighbors: ['gNB_001_C1', 'gNB_002_C2', 'gNB_005_C1'] },
  { id: 'gNB_002_C2', siteId: 'SITE_002', region: 'North', vendor: 'Ericsson', nrBand: 'n77', networkSlice: 'eMBB', lat: 48.8766, lng: 2.3822, status: 'normal', rsrp: -78, sinr: 22, throughput: 680, latency: 18, neighbors: ['gNB_001_C2', 'gNB_002_C1'] },
  { id: 'gNB_003_C1', siteId: 'SITE_003', region: 'East', vendor: 'Huawei', nrBand: 'n79', networkSlice: 'mMTC', lat: 48.8366, lng: 2.4022, status: 'normal', rsrp: -88, sinr: 14, throughput: 380, latency: 28, neighbors: ['gNB_001_C1', 'gNB_003_C2'] },
  { id: 'gNB_003_C2', siteId: 'SITE_003', region: 'East', vendor: 'Huawei', nrBand: 'n79', networkSlice: 'eMBB', lat: 48.8366, lng: 2.4122, status: 'warning', rsrp: -95, sinr: 6, throughput: 200, latency: 65, neighbors: ['gNB_003_C1', 'gNB_006_C1'] },
  { id: 'gNB_004_C1', siteId: 'SITE_004', region: 'South', vendor: 'Nokia', nrBand: 'n78', networkSlice: 'eMBB', lat: 48.7966, lng: 2.3322, status: 'normal', rsrp: -80, sinr: 20, throughput: 580, latency: 20, neighbors: ['gNB_001_C3', 'gNB_004_C2'] },
  { id: 'gNB_004_C2', siteId: 'SITE_004', region: 'South', vendor: 'Nokia', nrBand: 'n78', networkSlice: 'URLLC', lat: 48.7966, lng: 2.3222, status: 'normal', rsrp: -83, sinr: 17, throughput: 490, latency: 24, neighbors: ['gNB_004_C1', 'gNB_007_C1'] },
  { id: 'gNB_005_C1', siteId: 'SITE_005', region: 'West', vendor: 'Ericsson', nrBand: 'n77', networkSlice: 'eMBB', lat: 48.9166, lng: 2.2922, status: 'normal', rsrp: -86, sinr: 16, throughput: 420, latency: 26, neighbors: ['gNB_002_C1', 'gNB_005_C2'] },
  { id: 'gNB_005_C2', siteId: 'SITE_005', region: 'West', vendor: 'Ericsson', nrBand: 'n77', networkSlice: 'mMTC', lat: 48.9166, lng: 2.2822, status: 'critical', rsrp: -108, sinr: -2, throughput: 80, latency: 120, neighbors: ['gNB_005_C1', 'gNB_008_C1'] },
  { id: 'gNB_006_C1', siteId: 'SITE_006', region: 'East', vendor: 'Huawei', nrBand: 'n79', networkSlice: 'eMBB', lat: 48.8166, lng: 2.4322, status: 'normal', rsrp: -79, sinr: 21, throughput: 620, latency: 19, neighbors: ['gNB_003_C2', 'gNB_006_C2'] },
  { id: 'gNB_006_C2', siteId: 'SITE_006', region: 'East', vendor: 'Huawei', nrBand: 'n79', networkSlice: 'eMBB', lat: 48.8166, lng: 2.4422, status: 'warning', rsrp: -94, sinr: 7, throughput: 240, latency: 55, neighbors: ['gNB_006_C1'] },
  { id: 'gNB_007_C1', siteId: 'SITE_007', region: 'South', vendor: 'Nokia', nrBand: 'n78', networkSlice: 'URLLC', lat: 48.7766, lng: 2.3122, status: 'normal', rsrp: -81, sinr: 19, throughput: 540, latency: 21, neighbors: ['gNB_004_C2'] },
  { id: 'gNB_008_C1', siteId: 'SITE_008', region: 'West', vendor: 'Ericsson', nrBand: 'n77', networkSlice: 'eMBB', lat: 48.9366, lng: 2.2622, status: 'normal', rsrp: -84, sinr: 15, throughput: 460, latency: 27, neighbors: ['gNB_005_C2'] },
]

export const mockIncidents: Incident[] = [
  {
    id: 'RCA-2024-001',
    cellId: 'gNB_002_C1',
    siteId: 'SITE_002',
    region: 'North',
    timestamp: '2024-01-15T14:30:00Z',
    severity: 'critical',
    anomalyScore: 0.92,
    kpiSnapshot: {
      rsrp: -105, sinr: 2, prbUtilDL: 95, prbUtilUL: 88, cqi: 3,
      blerDL: 15, blerUL: 12, throughputDL: 120, throughputUL: 80,
      latency: 85, callDropRate: 8.5, hoSuccessRate: 65, mos: 2.1,
      mimoRank: 1, activeUsers: 450
    },
    rca: {
      predictedCause: 'Poor coverage + High interference',
      confidence: 0.89,
      topFeatures: [
        { feature: 'RSRP', importance: 0.32 },
        { feature: 'SINR', importance: 0.28 },
        { feature: 'Call Drop Rate', importance: 0.18 },
      ],
      similarCases: 12
    },
    remediation: {
      action: 'RF Optimization + Power Boost',
      steps: [
        'Increase RS power by 3dB',
        'Check neighboring cell interference',
        'Verify antenna alignment',
        'Schedule drive test for coverage validation'
      ],
      priority: 'High',
      effort: 'Medium',
      eta: 4,
      auto: false
    }
  },
  {
    id: 'RCA-2024-002',
    cellId: 'gNB_001_C3',
    siteId: 'SITE_001',
    region: 'North',
    timestamp: '2024-01-15T13:45:00Z',
    severity: 'medium',
    anomalyScore: 0.67,
    kpiSnapshot: {
      rsrp: -92, sinr: 8, prbUtilDL: 78, prbUtilUL: 72, cqi: 6,
      blerDL: 8, blerUL: 6, throughputDL: 280, throughputUL: 150,
      latency: 45, callDropRate: 4.2, hoSuccessRate: 78, mos: 3.2,
      mimoRank: 2, activeUsers: 320
    },
    rca: {
      predictedCause: 'DL capacity saturation',
      confidence: 0.74,
      topFeatures: [
        { feature: 'PRB Util DL', importance: 0.41 },
        { feature: 'Throughput DL', importance: 0.22 },
        { feature: 'Active Users', importance: 0.19 },
      ],
      similarCases: 8
    },
    remediation: {
      action: 'Load Balancing + Carrier Addition',
      steps: [
        'Enable load balancing to neighboring cells',
        'Consider CA activation',
        'Monitor user distribution'
      ],
      priority: 'Medium',
      effort: 'Low',
      eta: 2,
      auto: true
    }
  },
  {
    id: 'RCA-2024-003',
    cellId: 'gNB_005_C2',
    siteId: 'SITE_005',
    region: 'West',
    timestamp: '2024-01-15T12:20:00Z',
    severity: 'critical',
    anomalyScore: 0.96,
    kpiSnapshot: {
      rsrp: -108, sinr: -2, prbUtilDL: 45, prbUtilUL: 38, cqi: 2,
      blerDL: 25, blerUL: 20, throughputDL: 80, throughputUL: 40,
      latency: 120, callDropRate: 15, hoSuccessRate: 45, mos: 1.8,
      mimoRank: 1, activeUsers: 280
    },
    rca: {
      predictedCause: 'Hardware degradation / Antenna issue',
      confidence: 0.91,
      topFeatures: [
        { feature: 'RSRP', importance: 0.38 },
        { feature: 'SINR', importance: 0.31 },
        { feature: 'BLER DL', importance: 0.16 },
      ],
      similarCases: 5
    },
    remediation: {
      action: 'Emergency Maintenance Required',
      steps: [
        'Dispatch field engineer immediately',
        'Check antenna connections',
        'Verify RRU status',
        'Consider cell lockdown if service unusable'
      ],
      priority: 'Critical',
      effort: 'High',
      eta: 1,
      auto: false
    }
  },
  {
    id: 'RCA-2024-004',
    cellId: 'gNB_003_C2',
    siteId: 'SITE_003',
    region: 'East',
    timestamp: '2024-01-15T11:10:00Z',
    severity: 'high',
    anomalyScore: 0.78,
    kpiSnapshot: {
      rsrp: -95, sinr: 6, prbUtilDL: 82, prbUtilUL: 75, cqi: 5,
      blerDL: 12, blerUL: 10, throughputDL: 200, throughputUL: 120,
      latency: 65, callDropRate: 5.8, hoSuccessRate: 72, mos: 2.8,
      mimoRank: 2, activeUsers: 380
    },
    rca: {
      predictedCause: 'High interference + Capacity issue',
      confidence: 0.82,
      topFeatures: [
        { feature: 'SINR', importance: 0.35 },
        { feature: 'PRB Util DL', importance: 0.29 },
        { feature: 'Latency', importance: 0.17 },
      ],
      similarCases: 15
    }
  },
  {
    id: 'RCA-2024-005',
    cellId: 'gNB_006_C2',
    siteId: 'SITE_006',
    region: 'East',
    timestamp: '2024-01-15T10:55:00Z',
    severity: 'medium',
    anomalyScore: 0.71,
    kpiSnapshot: {
      rsrp: -94, sinr: 7, prbUtilDL: 75, prbUtilUL: 68, cqi: 5,
      blerDL: 9, blerUL: 7, throughputDL: 240, throughputUL: 140,
      latency: 55, callDropRate: 4.8, hoSuccessRate: 75, mos: 3.0,
      mimoRank: 2, activeUsers: 350
    },
    rca: {
      predictedCause: 'Congestion during peak hours',
      confidence: 0.76,
      topFeatures: [
        { feature: 'Active Users', importance: 0.33 },
        { feature: 'PRB Util DL', importance: 0.28 },
        { feature: 'Latency', importance: 0.21 },
      ],
      similarCases: 22
    }
  },
]

export const mockUsers: User[] = [
  { id: '1', name: 'Admin User', email: 'admin@qosbuddy.com', role: 'admin', notifications: true, createdAt: '2024-01-01' },
  { id: '2', name: 'Network Engineer', email: 'engineer@qosbuddy.com', role: 'engineer', notifications: true, createdAt: '2024-01-05' },
  { id: '3', name: 'Viewer User', email: 'viewer@qosbuddy.com', role: 'viewer', notifications: false, createdAt: '2024-01-10' },
]
