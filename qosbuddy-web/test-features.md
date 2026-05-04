# QoSBuddy Web App Feature Test Guide

## Test Checklist

### 1. WebSocket Connection
- [ ] Open dashboard at `http://localhost:3000/dashboard`
- [ ] Verify "Live Stream Connected" status is green
- [ ] Check events counter is updating
- [ ] Ensure auto-reconnect works if connection drops

### 2. Critical Anomaly Notifications
- [ ] Check for notification permission banner on first load
- [ ] Click "Enable Notifications" and grant permission
- [ ] Wait for a critical/high severity anomaly
- [ ] Verify browser notification appears with:
  - Title: "Critical Alert: [CELL_ID]"
  - Body: Root cause description
  - Icon: favicon.ico
  - Requires interaction: true

### 3. Incidents Page
- [ ] Navigate to `http://localhost:3000/incidents`
- [ ] Verify incidents are populated from WebSocket (not mock data)
- [ ] Check filtering by severity works
- [ ] Test search functionality
- [ ] Click on incident to see detail panel

### 4. Report Downloads
- [ ] Test PDF download:
  - Click PDF icon on any incident
  - Verify PDF opens with complete report
  - Check all sections: Details, RCA, KPI, Remediation
- [ ] Test CSV export:
  - Click "Export CSV" button
  - Verify CSV downloads with all incidents
  - Check headers and data format

### 5. Map Integration
- [ ] Navigate to `http://localhost:3000/map`
- [ ] Verify cells display at correct coordinates
- [ ] Check region is correct (e.g., gNB_046_C3 shows "Kairouan")
- [ ] Click on cells to see details
- [ ] Verify anomaly states show correct colors

### 6. Real-time Updates
- [ ] Keep dashboard open
- [ ] Start detection agent: `python agents/detection_agent.py --mode stream`
- [ ] Watch for new events appearing in real-time
- [ ] Verify incidents page updates automatically

## Troubleshooting

### If incidents are empty:
1. Check WebSocket connection status
2. Verify remediation agent is running on port 8765
3. Check browser console for errors

### If notifications don't work:
1. Check browser notification permissions
2. Verify critical events are being generated
3. Check browser console for notification errors

### If PDF download fails:
1. Check jsPDF library is loaded
2. Verify incident data structure is correct
3. Check browser console for errors

## Required Services

Make sure these are running:
1. **Web App**: `npm run dev` (port 3000)
2. **Detection Agent**: `python agents/detection_agent.py --mode stream`
3. **Remediation Agent**: `python agents/remediation_agent.py`
4. **Database**: MySQL/MariaDB with correct schema
