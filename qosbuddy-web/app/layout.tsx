import type { Metadata } from 'next'
import './globals.css'
import { NotificationProvider } from '@/lib/notifications'

export const metadata: Metadata = {
  title: 'QoSBuddy - Network Quality Monitoring',
  description: '5G Network QoS Monitoring, Anomaly Detection & Remediation',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <NotificationProvider>
          {children}
        </NotificationProvider>
      </body>
    </html>
  )
}
