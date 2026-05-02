'use client'

import { useEffect, useState, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Circle, useMap } from 'react-leaflet'
import { Icon, LatLngTuple } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {
  MapPin,
  Radio,
  Filter,
  Search,
  AlertTriangle,
  Zap,
  Activity,
  X
} from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { useWebSocket, RCAEvent } from '@/lib/websocket'
import { cn } from '@/lib/utils'

// Fix Leaflet default icon issue in Next.js
const defaultIcon = new Icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
})

// Cell status colors
const statusColors = {
  normal: '#10b981',
  warning: '#f59e0b', 
  critical: '#f43f5e',
  offline: '#64748b'
}

// Tunis region cell coordinates (approximate for demo)
const cellLocations: Record<string, LatLngTuple> = {
  'gNB_001_C1': [36.8065, 10.1815], // Tunis center
  'gNB_001_C2': [36.8165, 10.1915],
  'gNB_001_C3': [36.7965, 10.1715],
  'gNB_002_C1': [36.8265, 10.1515], // La Marsa
  'gNB_002_C2': [36.8365, 10.1415],
  'gNB_002_C3': [36.8165, 10.1615],
  'gNB_003_C1': [36.7765, 10.2015], // Carthage
  'gNB_003_C2': [36.7665, 10.2115],
  'gNB_003_C3': [36.7865, 10.1915],
  'gNB_004_C1': [36.8465, 10.2215], // Ariana
  'gNB_004_C2': [36.8565, 10.2315],
  'gNB_004_C3': [36.8365, 10.2115],
  'gNB_005_C1': [36.7565, 10.1315], // Sidi Bou Said
  'gNB_005_C2': [36.7465, 10.1215],
  'gNB_005_C3': [36.7665, 10.1415],
}

// Component to fit bounds when cells change
function MapBounds({ cells }: { cells: string[] }) {
  const map = useMap()
  
  useEffect(() => {
    if (cells.length > 0) {
      const positions = cells
        .map(id => cellLocations[id])
        .filter(Boolean) as LatLngTuple[]
      
      if (positions.length > 0) {
        map.fitBounds(positions, { padding: [50, 50] })
      }
    }
  }, [map, cells])
  
  return null
}

export default function MapPage() {
  const { events, isConnected } = useWebSocket('ws://localhost:8085')
  const [selectedCell, setSelectedCell] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  
  // Get unique cells from events
  const cells = useMemo(() => {
    const uniqueCells = new Map<string, RCAEvent & { status: string }>()
    
    // Add cells from events
    events.forEach(event => {
      const severity = event.anomaly_severity
      const status = severity === 'critical' || severity === 'high' ? 'critical' :
                     severity === 'medium' ? 'warning' : 'normal'
      
      // Keep the most severe status
      const existing = uniqueCells.get(event.cell_id)
      if (!existing || 
          (status === 'critical' && existing.status !== 'critical') ||
          (status === 'warning' && existing.status === 'normal')) {
        uniqueCells.set(event.cell_id, { ...event, status })
      }
    })
    
    // Add mock cells that haven't reported yet
    Object.keys(cellLocations).forEach(cellId => {
      if (!uniqueCells.has(cellId)) {
        uniqueCells.set(cellId, {
          rca_event_id: '',
          agent: '',
          phase: '',
          processed_at: '',
          source_event_id: '',
          timestamp: '',
          cell_id: cellId,
          region: 'Tunis',
          vendor: 'Nokia',
          nr_band: 'n78',
          network_slice: 'eMBB',
          anomaly_severity: 'low',
          anomaly_score: 0,
          kpi_snapshot: {},
          rule_engine: {},
          rca: {},
          remediation: undefined,
          status: 'normal'
        } as RCAEvent & { status: string })
      }
    })
    
    return Array.from(uniqueCells.values())
  }, [events])
  
  // Filter cells
  const filteredCells = useMemo(() => {
    return cells.filter(cell => {
      const matchesSearch = cell.cell_id.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesStatus = statusFilter === 'all' || cell.status === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [cells, searchQuery, statusFilter])
  
  // Stats
  const stats = useMemo(() => ({
    total: cells.length,
    normal: cells.filter(c => c.status === 'normal').length,
    warning: cells.filter(c => c.status === 'warning').length,
    critical: cells.filter(c => c.status === 'critical').length
  }), [cells])
  
  // Default center (Tunis)
  const defaultCenter: LatLngTuple = [36.8065, 10.1815]
  
  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        {/* Connection Status */}
        <div className={cn(
          'px-4 py-1 text-xs font-medium flex items-center gap-2',
          isConnected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
        )}>
          <div className={cn('w-2 h-2 rounded-full', isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500')} />
          {isConnected ? 'Live' : 'Offline'} • {stats.total} cells monitored
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar Panel */}
          <div className="w-80 bg-navy-800 border-r border-navy-500/30 flex flex-col">
            {/* Search & Filter */}
            <div className="p-4 border-b border-navy-500/30 space-y-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-navy-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search cells..."
                  className="w-full pl-9 pr-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-sm text-white focus:outline-none focus:border-accent-blue"
                />
              </div>
              
              <div className="flex gap-2">
                {['all', 'normal', 'warning', 'critical'].map((status) => (
                  <button
                    key={status}
                    onClick={() => setStatusFilter(status)}
                    className={cn(
                      'px-2 py-1 text-xs rounded-lg capitalize transition-colors',
                      statusFilter === status
                        ? 'bg-accent-blue text-white'
                        : 'bg-navy-700 text-navy-400 hover:bg-navy-600'
                    )}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Stats */}
            <div className="p-4 border-b border-navy-500/30">
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-navy-700/50 rounded-lg p-2">
                  <p className="text-2xl font-bold text-white">{stats.total}</p>
                  <p className="text-xs text-navy-400">Total Cells</p>
                </div>
                <div className="bg-emerald-500/10 rounded-lg p-2">
                  <p className="text-2xl font-bold text-emerald-400">{stats.normal}</p>
                  <p className="text-xs text-emerald-400/70">Normal</p>
                </div>
                <div className="bg-amber-500/10 rounded-lg p-2">
                  <p className="text-2xl font-bold text-amber-400">{stats.warning}</p>
                  <p className="text-xs text-amber-400/70">Warning</p>
                </div>
                <div className="bg-rose-500/10 rounded-lg p-2">
                  <p className="text-2xl font-bold text-rose-400">{stats.critical}</p>
                  <p className="text-xs text-rose-400/70">Critical</p>
                </div>
              </div>
            </div>
            
            {/* Cell List */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {filteredCells.map((cell) => (
                <button
                  key={cell.cell_id}
                  onClick={() => setSelectedCell(cell.cell_id)}
                  className={cn(
                    'w-full p-3 rounded-lg text-left transition-colors',
                    selectedCell === cell.cell_id
                      ? 'bg-accent-blue/20 border border-accent-blue/50'
                      : 'bg-navy-700/30 hover:bg-navy-700/50 border border-transparent'
                  )}
                >
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: statusColors[cell.status as keyof typeof statusColors] }}
                    />
                    <span className="font-medium text-white text-sm">{cell.cell_id}</span>
                  </div>
                  <p className="text-xs text-navy-400 mt-1 ml-5">
                    {cell.anomaly_severity !== 'low' ? cell.rca?.primary_cause || 'Issue detected' : 'Operating normally'}
                  </p>
                </button>
              ))}
            </div>
          </div>
          
          {/* Map */}
          <div className="flex-1 relative">
            <MapContainer
              center={defaultCenter}
              zoom={13}
              style={{ height: '100%', width: '100%' }}
              className="z-0"
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              
              <MapBounds cells={filteredCells.map(c => c.cell_id)} />
              
              {filteredCells.map((cell) => {
                const position = cellLocations[cell.cell_id]
                if (!position) return null
                
                const color = statusColors[cell.status as keyof typeof statusColors]
                const isSelected = selectedCell === cell.cell_id
                
                return (
                  <div key={cell.cell_id}>
                    {/* Coverage circle */}
                    <Circle
                      center={position}
                      radius={500}
                      pathOptions={{
                        color: color,
                        fillColor: color,
                        fillOpacity: isSelected ? 0.3 : 0.1,
                        weight: isSelected ? 3 : 1
                      }}
                    />
                    
                    {/* Marker */}
                    <Marker
                      position={position}
                      icon={defaultIcon}
                      eventHandlers={{
                        click: () => setSelectedCell(cell.cell_id)
                      }}
                    >
                      <Popup>
                        <div className="p-2 min-w-[200px]">
                          <h3 className="font-bold text-navy-900">{cell.cell_id}</h3>
                          <p className="text-sm text-gray-600">{cell.region} • {cell.vendor}</p>
                          <div className="mt-2 flex items-center gap-2">
                            <span
                              className="w-2 h-2 rounded-full"
                              style={{ backgroundColor: color }}
                            />
                            <span className="text-sm capitalize">{cell.status}</span>
                          </div>
                          {cell.anomaly_severity !== 'low' && (
                            <div className="mt-2 p-2 bg-rose-50 rounded">
                              <p className="text-xs text-rose-700">
                                <AlertTriangle className="w-3 h-3 inline mr-1" />
                                {cell.rca?.primary_cause || 'Anomaly detected'}
                              </p>
                            </div>
                          )}
                        </div>
                      </Popup>
                    </Marker>
                  </div>
                )
              })}
            </MapContainer>
            
            {/* Selected Cell Panel */}
            {selectedCell && (
              <div className="absolute bottom-4 right-4 w-80 bg-navy-800/95 backdrop-blur rounded-xl border border-navy-500/30 p-4 shadow-2xl">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <Radio className="w-4 h-4 text-accent-blue" />
                    {selectedCell}
                  </h3>
                  <button
                    onClick={() => setSelectedCell(null)}
                    className="p-1 hover:bg-navy-700 rounded-lg"
                  >
                    <X className="w-4 h-4 text-navy-400" />
                  </button>
                </div>
                
                {(() => {
                  const cell = cells.find(c => c.cell_id === selectedCell)
                  if (!cell) return null
                  
                  return (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: statusColors[cell.status as keyof typeof statusColors] }}
                        />
                        <span className="text-sm text-navy-300 capitalize">{cell.status}</span>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="bg-navy-700/50 p-2 rounded">
                          <p className="text-navy-400">Region</p>
                          <p className="text-white">{cell.region}</p>
                        </div>
                        <div className="bg-navy-700/50 p-2 rounded">
                          <p className="text-navy-400">Vendor</p>
                          <p className="text-white">{cell.vendor}</p>
                        </div>
                        <div className="bg-navy-700/50 p-2 rounded">
                          <p className="text-navy-400">Band</p>
                          <p className="text-white">{cell.nr_band}</p>
                        </div>
                        <div className="bg-navy-700/50 p-2 rounded">
                          <p className="text-navy-400">Slice</p>
                          <p className="text-white">{cell.network_slice}</p>
                        </div>
                      </div>
                      
                      {cell.anomaly_severity !== 'low' && (
                        <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg">
                          <p className="text-sm text-rose-400 flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4" />
                            {cell.rca?.primary_cause || 'Issue detected'}
                          </p>
                          <p className="text-xs text-navy-400 mt-1">
                            Score: {cell.anomaly_score?.toFixed(3)}
                          </p>
                        </div>
                      )}
                      
                      {cell.remediation && (
                        <div className="p-3 bg-accent-cyan/10 border border-accent-cyan/20 rounded-lg">
                          <p className="text-sm text-accent-cyan flex items-center gap-2">
                            <Zap className="w-4 h-4" />
                            AI Recommendation
                          </p>
                          <p className="text-xs text-navy-300 mt-1">
                            {cell.remediation.primary_action?.action || cell.remediation.cause}
                          </p>
                        </div>
                      )}
                    </div>
                  )
                })()}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
