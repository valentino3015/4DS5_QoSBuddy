'use client'

import { Bell, Search, User } from 'lucide-react'
import { mockUsers } from '@/lib/data'

export default function Header() {
  const user = mockUsers[0]

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
      <div className="flex items-center gap-4">
        {/* Notifications */}
        <button className="relative p-2 rounded-lg hover:bg-navy-700 text-navy-400 hover:text-white transition-colors">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-rose-500 rounded-full animate-pulse" />
        </button>

        {/* User */}
        <div className="flex items-center gap-3 pl-4 border-l border-navy-500/30">
          <div className="text-right hidden sm:block">
            <p className="text-sm font-medium text-white">{user.name}</p>
            <p className="text-xs text-navy-400 capitalize">{user.role}</p>
          </div>
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-accent-purple to-accent-blue flex items-center justify-center">
            <User className="w-5 h-5 text-white" />
          </div>
        </div>
      </div>
    </header>
  )
}
