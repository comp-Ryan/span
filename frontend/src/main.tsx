import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App.tsx'
import Report from './Report.tsx'

const reportId = /^\/report\/([^/?#]+)/.exec(location.pathname)?.[1]

createRoot(document.getElementById('root')!).render(
  reportId ? <Report id={decodeURIComponent(reportId)} /> : <App />
)
