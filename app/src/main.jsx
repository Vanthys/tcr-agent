import { createContext, useState, useContext, useEffect, useMemo } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import './index.css'
import App from './App.jsx'

export const ThemeContext = createContext({
  isDark: true,
  toggle: () => { },
})

const ThemeProvider = ({ children }) => {
  const [isDark, setIsDark] = useState(true)

  const toggle = () => {
    setIsDark(!isDark)
  }

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  const config = useMemo(() => ({
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: isDark ? '#4ecdc4' : '#38b2ac',
      borderRadius: 8,
      fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
      ...(isDark ? {
        colorBgBase: '#0d0d0d',
        colorBgContainer: '#111318',
        colorBgElevated: '#1a1d26',
      } : {
        colorBgBase: '#f0f2f5',
        colorBgContainer: '#ffffff',
        colorBgElevated: '#ffffff',
      })
    },
    components: {
      Layout: {
        headerBg: isDark ? '#111318' : '#ffffff',
        siderBg: isDark ? '#0d0f17' : '#ffffff',
        bodyBg: isDark ? '#0a0c12' : '#f0f2f5',
        headerHeight: 48,
        headerPadding: '0 16px',
      },
    }
  }), [isDark])

  return (
    <ThemeContext.Provider value={{ isDark, toggle }}>
      <ConfigProvider theme={config}>
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  )
}

createRoot(document.getElementById('root')).render(
  <ThemeProvider>
    <App />
  </ThemeProvider>
)
