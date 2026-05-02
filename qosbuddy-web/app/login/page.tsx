'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Radio, Eye, EyeOff, Lock, Mail, ArrowRight } from 'lucide-react'

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')
    
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })
      
      const data = await res.json()
      
      if (!res.ok) {
        setError(data.error || 'Login failed')
        return
      }
      
      // Store user in localStorage for session
      localStorage.setItem('qosbuddy_user', JSON.stringify(data.user))
      window.location.href = '/dashboard'
    } catch (err) {
      setError('Network error. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-navy-900 via-navy-800 to-navy-900 p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-accent-blue to-accent-cyan flex items-center justify-center glow-blue">
            <Radio className="w-7 h-7 text-white" />
          </div>
          <span className="text-2xl font-bold text-white">QoSBuddy</span>
        </div>

        {/* Card */}
        <div className="glass rounded-2xl p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-white mb-2">Welcome back</h1>
            <p className="text-navy-400">Sign in to your account</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="p-3 bg-rose-500/20 border border-rose-500/30 rounded-lg text-rose-400 text-sm">
                {error}
              </div>
            )}
            
            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-navy-400 mb-2">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-navy-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-11 pr-4 py-3 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white placeholder-navy-400 focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue transition-all"
                  placeholder="Enter your email"
                  required
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm font-medium text-navy-400 mb-2">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-navy-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-11 pr-11 py-3 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white placeholder-navy-400 focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue transition-all"
                  placeholder="Enter your password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-navy-400 hover:text-white"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            {/* Remember & Forgot */}
            <div className="flex items-center justify-between text-sm">
              <label className="flex items-center gap-2 text-navy-400 cursor-pointer">
                <input type="checkbox" className="w-4 h-4 rounded border-navy-500 bg-navy-700 text-accent-blue focus:ring-accent-blue" />
                Remember me
              </label>
              <Link href="#" className="text-accent-blue hover:text-accent-cyan transition-colors">
                Forgot password?
              </Link>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 bg-gradient-to-r from-accent-blue to-accent-cyan text-white font-semibold rounded-lg hover:opacity-90 transition-opacity flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  Sign in <ArrowRight className="w-5 h-5" />
                </>
              )}
            </button>
          </form>

          {/* Demo accounts */}
          <div className="mt-8 pt-6 border-t border-navy-500/30">
            <p className="text-sm text-navy-400 text-center mb-4">Demo Accounts (Password: admin123)</p>
            <div className="grid grid-cols-3 gap-2">
              {[
                { role: 'Admin', email: 'admin@qosbuddy.com' },
                { role: 'Engineer', email: 'engineer@example.com' },
                { role: 'Viewer', email: 'viewer@example.com' }
              ].map(({ role, email }) => (
                <button
                  key={role}
                  onClick={() => {
                    setEmail(email)
                    setPassword('admin123')
                  }}
                  className="px-3 py-2 text-xs bg-navy-700/50 hover:bg-navy-700 text-navy-300 rounded-lg transition-colors"
                >
                  {role}
                </button>
              ))}
            </div>
          </div>
        </div>

        <p className="text-center text-navy-400 text-sm mt-6">
          Don&apos;t have an account?{' '}
          <Link href="#" className="text-accent-blue hover:text-accent-cyan transition-colors">
            Contact administrator
          </Link>
        </p>
      </div>
    </div>
  )
}
