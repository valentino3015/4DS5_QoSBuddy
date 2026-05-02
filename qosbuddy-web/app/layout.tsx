import type { Metadata } from 'next'
import './globals.css'

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
      <body className="antialiased">{children}</body>
    </html>
  )
}
