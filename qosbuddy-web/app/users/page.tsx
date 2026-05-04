'use client'

import { useState, useEffect } from 'react'
import {
  Users,
  Search,
  Plus,
  MoreVertical,
  Mail,
  Shield,
  User as UserIcon,
  Check,
  X,
  Loader2
} from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { cn } from '@/lib/utils'

interface User {
  id: number
  name: string
  email: string
  role: string
  notifications_enabled?: boolean
  created_at?: string
}

export default function UsersPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedRole, setSelectedRole] = useState<string>('all')
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const response = await fetch('/api/users')
        if (response.ok) {
          const data = await response.json()
          setUsers(data)
        }
      } catch (error) {
        console.error('Failed to fetch users:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchUsers()
  }, [])

  const filteredUsers = users.filter(user => {
    if (selectedRole !== 'all' && user.role !== selectedRole) return false
    if (searchTerm && !user.name?.toLowerCase().includes(searchTerm.toLowerCase()) &&
        !user.email?.toLowerCase().includes(searchTerm.toLowerCase())) return false
    return true
  })

  const getRoleIcon = (role: string) => {
    switch (role) {
      case 'admin': return <Shield className="w-4 h-4 text-accent-purple" />
      case 'engineer': return <UserIcon className="w-4 h-4 text-accent-blue" />
      default: return <UserIcon className="w-4 h-4 text-navy-400" />
    }
  }

  const getRoleBadge = (role: string) => {
    const classes = {
      admin: 'bg-accent-purple/20 text-accent-purple',
      engineer: 'bg-accent-blue/20 text-accent-blue',
      viewer: 'bg-navy-600 text-navy-300'
    }
    return (
      <span className={cn('px-2 py-0.5 rounded text-xs font-medium', classes[role as keyof typeof classes])}>
        {role.charAt(0).toUpperCase() + role.slice(1)}
      </span>
    )
  }

  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                <Users className="w-6 h-6 text-accent-purple" />
                Users
              </h1>
              <p className="text-navy-400 mt-1">Manage team members and permissions</p>
            </div>
            <button className="flex items-center gap-2 px-4 py-2 bg-accent-blue hover:bg-accent-blue/80 rounded-lg text-white font-medium transition-colors">
              <Plus className="w-4 h-4" />
              Add User
            </button>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-4 mb-6">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-navy-400" />
              <input
                type="text"
                placeholder="Search users..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-navy-800 border border-navy-500/50 rounded-lg text-sm text-white placeholder-navy-400 focus:outline-none focus:border-accent-blue"
              />
            </div>
            <select
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value)}
              className="px-4 py-2 bg-navy-800 border border-navy-500/50 rounded-lg text-sm text-white focus:outline-none focus:border-accent-blue"
            >
              <option value="all">All Roles</option>
              <option value="admin">Admin</option>
              <option value="engineer">Engineer</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>

          {/* Users Table */}
          <div className="glass rounded-xl overflow-hidden">
            <table className="w-full">
              <thead className="bg-navy-700/50">
                <tr className="text-left text-xs text-navy-400">
                  <th className="px-6 py-4 font-medium">User</th>
                  <th className="px-6 py-4 font-medium">Role</th>
                  <th className="px-6 py-4 font-medium">Status</th>
                  <th className="px-6 py-4 font-medium">Notifications</th>
                  <th className="px-6 py-4 font-medium">Created</th>
                  <th className="px-6 py-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="text-sm">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center">
                      <Loader2 className="w-6 h-6 animate-spin mx-auto text-accent-blue" />
                      <p className="text-navy-400 mt-2">Loading users...</p>
                    </td>
                  </tr>
                ) : filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center text-navy-400">
                      No users found
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((user) => (
                    <tr key={user.id} className="border-b border-navy-500/20 hover:bg-navy-700/30 transition-colors">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center">
                            <span className="text-white font-medium">{user.name?.charAt(0) || '?'}</span>
                          </div>
                          <div>
                            <p className="text-white font-medium">{user.name}</p>
                            <p className="text-navy-400 text-xs">{user.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">{getRoleBadge(user.role)}</td>
                      <td className="px-6 py-4">
                        <span className="flex items-center gap-1.5 text-emerald-400">
                          <div className="w-2 h-2 rounded-full bg-emerald-500" />
                          Active
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        {user.notifications_enabled ? (
                          <Check className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <X className="w-4 h-4 text-navy-400" />
                        )}
                      </td>
                      <td className="px-6 py-4 text-navy-400">{user.created_at ? new Date(user.created_at).toLocaleDateString() : '-'}</td>
                      <td className="px-6 py-4">
                        <button className="p-2 hover:bg-navy-700 rounded-lg text-navy-400 hover:text-white transition-colors">
                          <MoreVertical className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </main>
      </div>
    </div>
  )
}
