'use client'

import { useState } from 'react'
import {
  Settings,
  Bell,
  Shield,
  Database,
  Radio,
  Save,
  Check
} from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import { cn } from '@/lib/utils'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('general')
  const [saved, setSaved] = useState(false)

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const tabs = [
    { id: 'general', name: 'General', icon: Settings },
    { id: 'notifications', name: 'Notifications', icon: Bell },
    { id: 'security', name: 'Security', icon: Shield },
    { id: 'api', name: 'API & Integrations', icon: Database },
    { id: 'network', name: 'Network Config', icon: Radio },
  ]

  return (
    <div className="flex h-screen bg-navy-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-hidden flex">
          {/* Sidebar */}
          <div className="w-64 bg-navy-800 border-r border-navy-500/30 p-4">
            <h2 className="text-lg font-semibold text-white mb-4">Settings</h2>
            <nav className="space-y-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
                    activeTab === tab.id
                      ? 'bg-accent-blue/10 text-accent-blue'
                      : 'text-navy-400 hover:bg-navy-700 hover:text-white'
                  )}
                >
                  <tab.icon className="w-4 h-4" />
                  {tab.name}
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-2xl">
              {activeTab === 'general' && (
                <div className="space-y-6">
                  <h3 className="text-xl font-semibold text-white">General Settings</h3>
                  
                  <div className="glass rounded-xl p-5 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">Organization Name</label>
                      <input
                        type="text"
                        defaultValue="QoSBuddy Network"
                        className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">Timezone</label>
                      <select className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue">
                        <option>UTC (GMT+0)</option>
                        <option>Europe/Paris (GMT+1)</option>
                        <option>America/New_York (GMT-5)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">Data Retention (days)</label>
                      <input
                        type="number"
                        defaultValue="90"
                        className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue"
                      />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'notifications' && (
                <div className="space-y-6">
                  <h3 className="text-xl font-semibold text-white">Notification Preferences</h3>
                  
                  <div className="glass rounded-xl p-5 space-y-4">
                    {[
                      { label: 'Critical Incidents', desc: 'Immediate alerts for critical anomalies', checked: true },
                      { label: 'Daily Summary', desc: 'Daily digest of network health', checked: true },
                      { label: 'Remediation Complete', desc: 'When AI actions are executed', checked: false },
                      { label: 'System Updates', desc: 'New features and maintenance', checked: true },
                    ].map((item, idx) => (
                      <label key={idx} className="flex items-start gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          defaultChecked={item.checked}
                          className="mt-1 w-4 h-4 rounded border-navy-500"
                        />
                        <div>
                          <p className="text-sm font-medium text-white">{item.label}</p>
                          <p className="text-xs text-navy-400">{item.desc}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {activeTab === 'security' && (
                <div className="space-y-6">
                  <h3 className="text-xl font-semibold text-white">Security Settings</h3>
                  
                  <div className="glass rounded-xl p-5 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">Session Timeout (minutes)</label>
                      <input
                        type="number"
                        defaultValue="30"
                        className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">Max Login Attempts</label>
                      <input
                        type="number"
                        defaultValue="5"
                        className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue"
                      />
                    </div>
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-navy-500" />
                      <span className="text-sm text-navy-300">Require 2FA for admin users</span>
                    </label>
                  </div>
                </div>
              )}

              {activeTab === 'api' && (
                <div className="space-y-6">
                  <h3 className="text-xl font-semibold text-white">API Configuration</h3>
                  
                  <div className="glass rounded-xl p-5 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">API Key</label>
                      <div className="flex gap-2">
                        <input
                          type="password"
                          value="••••••••••••••••••••••••"
                          readOnly
                          className="flex-1 px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white"
                        />
                        <button className="px-4 py-2 bg-navy-700 hover:bg-navy-600 rounded-lg text-white text-sm">
                          Regenerate
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">LLM API Endpoint</label>
                      <input
                        type="text"
                        defaultValue="http://localhost:8081"
                        className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">Webhook URL</label>
                      <input
                        type="text"
                        placeholder="https://your-webhook.com/endpoint"
                        className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue"
                      />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'network' && (
                <div className="space-y-6">
                  <h3 className="text-xl font-semibold text-white">Network Configuration</h3>
                  
                  <div className="glass rounded-xl p-5 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">Anomaly Threshold (%)</label>
                      <input
                        type="number"
                        defaultValue="75"
                        className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-navy-300 mb-2">Auto-remediation</label>
                      <select className="w-full px-3 py-2 bg-navy-700/50 border border-navy-500/50 rounded-lg text-white focus:outline-none focus:border-accent-blue">
                        <option>Enabled - Low severity only</option>
                        <option>Enabled - All severities</option>
                        <option>Disabled</option>
                      </select>
                    </div>
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-navy-500" />
                      <span className="text-sm text-navy-300">Enable neighbor correlation analysis</span>
                    </label>
                  </div>
                </div>
              )}

              {/* Save Button */}
              <div className="mt-8 flex items-center gap-4">
                <button
                  onClick={handleSave}
                  className={cn(
                    'px-6 py-2.5 rounded-lg text-white font-medium transition-all flex items-center gap-2',
                    saved ? 'bg-emerald-500' : 'bg-accent-blue hover:bg-accent-blue/80'
                  )}
                >
                  {saved ? <><Check className="w-4 h-4" /> Saved</> : <><Save className="w-4 h-4" /> Save Changes</>}
                </button>
                <button className="px-6 py-2.5 bg-navy-700 hover:bg-navy-600 rounded-lg text-white font-medium transition-colors">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
