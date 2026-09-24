import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

const greenTheme = {
  token: {
    colorPrimary: '#22c55e',
    colorSuccess: '#16a34a',
    colorInfo: '#22c55e',
    colorLink: '#16a34a',
    borderRadius: 6,
  },
  algorithm: theme.defaultAlgorithm,
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={greenTheme}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)


