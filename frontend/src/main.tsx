import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App.tsx'
import Report from './Report.tsx'
import Home from './Home.tsx'
import GetPaid from './GetPaid.tsx'
import Reports from './Reports.tsx'
import { CustomerDetailPage, CustomersList } from './Customers.tsx'
import Sponsors from './Sponsors.tsx'

const path = location.pathname
const reportId = /^\/report\/([^/?#]+)/.exec(path)?.[1]
const customerId = /^\/customers\/([^/?#]+)\/?$/.exec(path)?.[1]
const is = (re: RegExp) => re.test(path)

createRoot(document.getElementById('root')!).render(
  reportId ? <Report id={decodeURIComponent(reportId)} />
    : is(/^\/home\/?$/) ? <Home />
    : is(/^\/get-paid\/?$/) ? <GetPaid />
    : is(/^\/reports\/?$/) ? <Reports />
    : customerId ? <CustomerDetailPage id={decodeURIComponent(customerId)} />
    : is(/^\/customers\/?$/) ? <CustomersList />
    : is(/^\/sponsors\/?$/) ? <Sponsors />
    : <App />
)
