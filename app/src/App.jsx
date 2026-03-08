import { Routes, Route } from 'react-router-dom'
import ExplorePage from './pages/ExplorePage'
import IngestPage from './pages/IngestPage'
import PastChatsPage from './pages/PastChatsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ExplorePage />} />
      <Route path="/ingest" element={<IngestPage />} />
      <Route path="/chats" element={<PastChatsPage />} />
    </Routes>
  )
}
