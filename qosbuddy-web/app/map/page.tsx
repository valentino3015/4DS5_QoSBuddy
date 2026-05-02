'use client'

import dynamic from 'next/dynamic'

const RealMap = dynamic(() => import('./real-map'), {
  ssr: false,
  loading: () => (
    <div className="flex h-screen bg-navy-900 items-center justify-center">
      <div className="text-navy-400">Loading map...</div>
    </div>
  )
})

export default function MapPage() {
  return <RealMap />
}
      rsrp: cell.rsrp,
      throughput: cell.throughput,
      neighbors: cell.neighbors,
      siteId: cell.siteId,
      region: cell.region,
      vendor: cell.vendor
    }
  })

  const filteredCells = cells.filter(cell => {
    if (filter !== 'all' && cell.status !== filter) return false
    if (searchTerm && !cell.id.toLowerCase().includes(searchTerm.toLowerCase())) return false
    return true
  })

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'normal': return '#10b981'
      case 'warning': return '#f59e0b'
      case 'critical': return '#f43f5e'
      default: return '#64748b'
    }
  }

  const getStatusBg = (status: string) => {
    switch (status) {
      case 'normal': return 'bg-emerald-500/20 border-emerald-500/50'
      case 'warning': return 'bg-amber-500/20 border-amber-500/50'
      case 'critical': return 'bg-rose-500/20 border-rose-500/50'
      default: return 'bg-slate-500/20 border-slate-500/50'
    }
  }

  const renderConnections = () => {
    const connections: JSX.Element[] = []
    filteredCells.forEach(cell => {
      cell.neighbors.forEach(neighborId => {
        const neighbor = filteredCells.find(c => c.id === neighborId)
        if (neighbor && cell.id < neighbor.id) {
          const isHighlighted = hoveredCell === cell.id || hoveredCell === neighbor.id
          connections.push(
            <line
              key={`${cell.id}-${neighborId}`}
              x1={cell.x}
              y1={cell.y}
              x2={neighbor.x}
              y2={neighbor.y}
              stroke={isHighlighted ? '#3b82f6' : '#334155'}
              strokeWidth={isHighlighted ? 3 : 1}
              strokeDasharray={isHighlighted ? undefined : '4,4'}
              opacity={isHighlighted ? 1 : 0.5}
              className="transition-all duration-300"
            />
          )
        }
      })
    })
    return connections
  }

  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-hidden flex">
          {/* Map Area */}
          <div className="flex-1 relative bg-gradient-to-br from-navy-900 via-navy-800 to-navy-900">
            {/* Grid Background */}
            <div className="absolute inset-0 opacity-10"
              style={{
                backgroundImage: `
                  linear-gradient(to right, #334155 1px, transparent 1px),
                  linear-gradient(to bottom, #334155 1px, transparent 1px)
                `,
                backgroundSize: '40px 40px'
              }}
            />

            {/* SVG Map */}
            <svg
              ref={svgRef}
              className="w-full h-full"
              viewBox="0 0 1000 600"
              preserveAspectRatio="xMidYMid meet"
            >
              {/* Connection lines */}
              {renderConnections()}

              {/* Cells */}
              {filteredCells.map(cell => {
                const isSelected = selectedCell?.id === cell.id
                const isHovered = hoveredCell === cell.id
                const color = getStatusColor(cell.status)

                return (
                  <g
                    key={cell.id}
                    transform={`translate(${cell.x}, ${cell.y})`}
                    className="cursor-pointer"
                    onClick={() => setSelectedCell(cell)}
                    onMouseEnter={() => setHoveredCell(cell.id)}
                    onMouseLeave={() => setHoveredCell(null)}
                  >
                    {/* Outer glow for selected/hovered */}
                    {(isSelected || isHovered) && (
                      <circle
                        r="35"
                        fill={color}
                        opacity="0.2"
                        className="animate-pulse"
                      />
                    )}
                    
                    {/* Cell tower base */}
                    <circle
                      r={isSelected ? 28 : 24}
                      fill={color}
                      opacity={isSelected ? 0.3 : 0.2}
                      stroke={color}
                      strokeWidth={isSelected ? 3 : 2}
                      className="transition-all duration-300"
                    />
                    
                    {/* Inner circle */}
                    <circle
                      r={isSelected ? 20 : 16}
                      fill={color}
                      opacity={0.8}
                      className="transition-all duration-300"
                    />

                    {/* Signal waves */}
                    <g opacity={0.5}>
                      <path
                        d="M -30,-10 Q -40,-20 -30,-30"
                        stroke={color}
                        strokeWidth="2"
                        fill="none"
                      />
                      <path
                        d="M 30,-10 Q 40,-20 30,-30"
                        stroke={color}
                        strokeWidth="2"
                        fill="none"
                      />
                    </g>

                    {/* Cell ID */}
                    <text
                      y="45"
                      textAnchor="middle"
                      fill="white"
                      fontSize="11"
                      fontWeight={isSelected ? 600 : 400}
                      className="pointer-events-none"
                    >
                      {cell.id.split('_')[1]}_{cell.id.split('_')[2]}
                    </text>

                    {/* Status indicator */}
                    <circle
                      cy="-30"
                      r="6"
                      fill={color}
                      stroke="#0f172a"
                      strokeWidth="2"
                    />
                  </g>
                )
              })}
            </svg>

            {/* Legend */}
            <div className="absolute bottom-4 left-4 glass rounded-lg p-3">
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-emerald-500" />
                  <span className="text-navy-300">Normal</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-amber-500" />
                  <span className="text-navy-300">Warning</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-rose-500" />
                  <span className="text-navy-300">Critical</span>
                </div>
              </div>
            </div>

            {/* Map Controls */}
            <div className="absolute top-4 right-4 flex flex-col gap-2">
              <button className="p-2 bg-navy-700 hover:bg-navy-600 rounded-lg transition-colors">
                <Layers className="w-5 h-5 text-navy-300" />
              </button>
              <button className="p-2 bg-navy-700 hover:bg-navy-600 rounded-lg transition-colors">
                <Filter className="w-5 h-5 text-navy-300" />
              </button>
            </div>
          </div>

          {/* Sidebar Panel */}
          <div className="w-80 bg-navy-800 border-l border-navy-500/30 overflow-y-auto">
            {/* Search & Filter */}
            <div className="p-4 border-b border-navy-500/30 space-y-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-navy-400" />
                <input
                  type="text"
                  placeholder="Search cells..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-sm text-white placeholder-navy-400 focus:outline-none focus:border-accent-blue"
                />
              </div>
              <div className="flex gap-2">
                {(['all', 'normal', 'warning', 'critical'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={cn(
                      'px-3 py-1.5 rounded-lg text-xs font-medium transition-all capitalize',
                      filter === f
                        ? 'bg-accent-blue text-white'
                        : 'bg-navy-700 text-navy-400 hover:bg-navy-600'
                    )}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>

            {/* Cell List */}
            <div className="p-4 space-y-3">
              <h3 className="text-sm font-semibold text-navy-400 uppercase tracking-wider">
                Cells ({filteredCells.length})
              </h3>
              {filteredCells.map(cell => (
                <div
                  key={cell.id}
                  onClick={() => setSelectedCell(cell)}
                  onMouseEnter={() => setHoveredCell(cell.id)}
                  onMouseLeave={() => setHoveredCell(null)}
                  className={cn(
                    'p-3 rounded-lg border cursor-pointer transition-all',
                    selectedCell?.id === cell.id
                      ? 'bg-accent-blue/10 border-accent-blue/50'
                      : 'bg-navy-700/50 border-navy-500/30 hover:border-navy-500/50'
                  )}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <div className={cn('p-1.5 rounded-lg', getStatusBg(cell.status))}>
                        <Radio className="w-4 h-4" style={{ color: getStatusColor(cell.status) }} />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white">{cell.id}</p>
                        <p className="text-xs text-navy-400">{cell.siteId}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-navy-400">RSRP</p>
                      <p className={cn(
                        'text-sm font-medium',
                        cell.rsrp > -90 ? 'text-emerald-400' : cell.rsrp > -100 ? 'text-amber-400' : 'text-rose-400'
                      )}>
                        {cell.rsrp} dBm
                      </p>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-4 text-xs text-navy-400">
                    <span className="flex items-center gap-1">
                      <Wifi className="w-3 h-3" />
                      {cell.throughput} Mbps
                    </span>
                    <span className="flex items-center gap-1">
                      <Signal className="w-3 h-3" />
                      {cell.neighbors.length} neighbors
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Selected Cell Details */}
            {selectedCell && (
              <div className="border-t border-navy-500/30 p-4">
                <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                  <Info className="w-4 h-4 text-accent-blue" />
                  Cell Details
                </h3>
                <div className="space-y-3">
                  <div className="p-3 bg-navy-700/50 rounded-lg">
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-navy-400">Region</p>
                        <p className="text-white font-medium">{selectedCell.region}</p>
                      </div>
                      <div>
                        <p className="text-navy-400">Vendor</p>
                        <p className="text-white font-medium">{selectedCell.vendor}</p>
                      </div>
                      <div>
                        <p className="text-navy-400">Throughput</p>
                        <p className="text-white font-medium">{selectedCell.throughput} Mbps</p>
                      </div>
                      <div>
                        <p className="text-navy-400">RSRP</p>
                        <p className={cn(
                          'font-medium',
                          selectedCell.rsrp > -90 ? 'text-emerald-400' : selectedCell.rsrp > -100 ? 'text-amber-400' : 'text-rose-400'
                        )}>
                          {selectedCell.rsrp} dBm
                        </p>
                      </div>
                    </div>
                  </div>

                  <div>
                    <p className="text-xs text-navy-400 mb-2">Neighboring Cells</p>
                    <div className="flex flex-wrap gap-2">
                      {selectedCell.neighbors.map(neighborId => {
                        const neighbor = cells.find(c => c.id === neighborId)
                        return (
                          <button
                            key={neighborId}
                            onClick={() => neighbor && setSelectedCell(neighbor)}
                            className={cn(
                              'px-2 py-1 rounded text-xs font-medium transition-colors',
                              neighbor?.status === 'normal' ? 'bg-emerald-500/20 text-emerald-400' :
                              neighbor?.status === 'warning' ? 'bg-amber-500/20 text-amber-400' :
                              'bg-rose-500/20 text-rose-400'
                            )}
                          >
                            {neighborId.split('_')[1]}_{neighborId.split('_')[2]}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
