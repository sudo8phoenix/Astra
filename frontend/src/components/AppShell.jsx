import Layout from './Layout'
import ProductivityPage from './ProductivityPage'

export default function AppShell({ route, onLogout, onNavigate }) {
  if (route === '/productivity') {
    return <ProductivityPage onBack={() => onNavigate('/')} />
  }

  return <Layout onLogout={onLogout} onNavigate={onNavigate} />
}
