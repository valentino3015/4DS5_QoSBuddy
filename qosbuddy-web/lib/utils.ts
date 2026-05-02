import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatNumber(num: number, decimals = 2): string {
  return num.toFixed(decimals)
}

export function getSeverityColor(severity: string): string {
  const colors: Record<string, string> = {
    normal: 'bg-emerald-500',
    low: 'bg-blue-500',
    medium: 'bg-amber-500',
    high: 'bg-orange-500',
    critical: 'bg-rose-500',
  }
  return colors[severity.toLowerCase()] || 'bg-gray-500'
}
