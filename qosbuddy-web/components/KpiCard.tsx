'use client'

import { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface KpiCardProps {
  title: string
  value: string | number
  unit?: string
  change?: number | string
  icon: LucideIcon
  color: 'blue' | 'cyan' | 'emerald' | 'amber' | 'rose' | 'purple'
  subtitle?: string
}

const colorClasses = {
  blue: 'from-accent-blue/20 to-accent-blue/5 border-accent-blue/30 text-accent-blue',
  cyan: 'from-accent-cyan/20 to-accent-cyan/5 border-accent-cyan/30 text-accent-cyan',
  emerald: 'from-accent-emerald/20 to-accent-emerald/5 border-accent-emerald/30 text-accent-emerald',
  amber: 'from-accent-amber/20 to-accent-amber/5 border-accent-amber/30 text-accent-amber',
  rose: 'from-accent-rose/20 to-accent-rose/5 border-accent-rose/30 text-accent-rose',
  purple: 'from-accent-purple/20 to-accent-purple/5 border-accent-purple/30 text-accent-purple',
}

const iconBgClasses = {
  blue: 'bg-accent-blue/20 text-accent-blue',
  cyan: 'bg-accent-cyan/20 text-accent-cyan',
  emerald: 'bg-accent-emerald/20 text-accent-emerald',
  amber: 'bg-accent-amber/20 text-accent-amber',
  rose: 'bg-accent-rose/20 text-accent-rose',
  purple: 'bg-accent-purple/20 text-accent-purple',
}

export default function KpiCard({ title, value, unit, change, icon: Icon, color, subtitle }: KpiCardProps) {
  return (
    <div className={cn(
      'relative overflow-hidden rounded-xl border bg-gradient-to-br p-5 transition-all hover:scale-[1.02]',
      colorClasses[color]
    )}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-navy-400 text-sm font-medium">{title}</p>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-bold text-white">{value}</span>
            {unit && <span className="text-sm text-navy-400">{unit}</span>}
          </div>
          {change !== undefined && (
            <div className="mt-1 flex items-center gap-1">
              {typeof change === 'number' ? (
                <span className={cn(
                  'text-xs font-medium',
                  change >= 0 ? 'text-emerald-400' : 'text-rose-400'
                )}>
                  {change >= 0 ? '+' : ''}{change}%
                </span>
              ) : (
                <span className="text-xs font-medium text-accent-cyan">{change}</span>
              )}
              {typeof change === 'number' && <span className="text-xs text-navy-400">vs last hour</span>}
            </div>
          )}
          {subtitle && <p className="mt-1 text-xs text-navy-400">{subtitle}</p>}
        </div>
        <div className={cn('p-2.5 rounded-lg', iconBgClasses[color])}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  )
}
