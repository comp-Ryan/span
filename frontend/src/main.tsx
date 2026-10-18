import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App.tsx'
import Report from './Report.tsx'
import Home from './Home.tsx'

const reportId = /^\/report\/([^/?#]+)/.exec(location.pathname)?.[1]
const isHome = /^\/home\/?$/.test(location.pathname)

createRoot(document.getElementById('root')!).render(
  reportId ? <Report id={decodeURIComponent(reportId)} /> : isHome ? <Home /> : <App />
)
