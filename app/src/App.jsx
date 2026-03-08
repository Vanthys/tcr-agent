import { Routes, Route } from 'react-router-dom'
import ExplorePage from './pages/ExplorePage'
import IngestPage from './pages/IngestPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ExplorePage />} />
      <Route path="/ingest" element={<IngestPage />} />
    </Routes>
  )
}
