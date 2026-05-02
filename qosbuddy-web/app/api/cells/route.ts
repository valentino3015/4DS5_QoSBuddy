import { NextRequest, NextResponse } from 'next/server'
import { readFileSync } from 'fs'
import { join } from 'path'
import { parse } from 'csv-parse/sync'

export interface CellTopology {
  cell_id: string
  site_id: string
  region: string
  latitude: number
  longitude: number
  vendor: string
  nr_band: string
  bandwidth_MHz: string
  max_tx_power_dBm: string
  antenna_tilt_deg: string
  antenna_azimuth_deg: string
  mimo_config: string
  network_slice: string
  neighbor_cells: string
  deployment_type: string
  active: string
  commissioned_date: string
}

interface CsvRecord {
  cell_id: string
  site_id: string
  region: string
  latitude: string
  longitude: string
  vendor: string
  nr_band: string
  bandwidth_MHz: string
  max_tx_power_dBm: string
  antenna_tilt_deg: string
  antenna_azimuth_deg: string
  mimo_config: string
  network_slice: string
  neighbor_cells: string
  deployment_type: string
  active: string
  commissioned_date: string
}

export async function GET(req: NextRequest) {
  try {
    const csvPath = join(process.cwd(), '..', 'data', 'cell_topology.csv')
    const fileContent = readFileSync(csvPath, 'utf-8')
    
    const records = parse(fileContent, {
      columns: true,
      skip_empty_lines: true,
      trim: true
    }) as CsvRecord[]
    
    // Convert string numbers to actual numbers
    const cells: CellTopology[] = records.map(r => ({
      ...r,
      latitude: parseFloat(r.latitude),
      longitude: parseFloat(r.longitude)
    }))
    
    return NextResponse.json({ cells, count: cells.length })
  } catch (error) {
    console.error('Error reading cell topology:', error)
    return NextResponse.json(
      { error: 'Failed to load cell topology', cells: [] },
      { status: 500 }
    )
  }
}
