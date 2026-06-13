import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from '@/components/Sidebar'
import Dashboard from '@/pages/Dashboard'
import RunDetail from '@/pages/RunDetail'
import Repositories from '@/pages/Repositories'
import RepoBrowse from '@/pages/RepoBrowse'
import Audit from '@/pages/Audit'
import ApiDocs from '@/pages/ApiDocs'
import CodeMap from '@/pages/CodeMap'
import Settings from '@/pages/Settings'

export default function App() {
  return (
    <div className="layout">
      <Sidebar />
      <div className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/repositories" element={<Repositories />} />
          <Route path="/repositories/:repositoryId/browse" element={<RepoBrowse />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/api-docs" element={<ApiDocs />} />
          <Route path="/code-map" element={<CodeMap />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </div>
    </div>
  )
}
