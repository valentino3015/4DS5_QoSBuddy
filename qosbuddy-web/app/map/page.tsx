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
