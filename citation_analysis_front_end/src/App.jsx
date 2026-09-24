import React, { useEffect, useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Spin, Menu, Dropdown, Avatar, Space } from 'antd'
import { LogoutOutlined, UserOutlined, DownOutlined } from '@ant-design/icons'
import LoginPage from './pages/LoginPage'
import TaskManagementPage from './pages/TaskManagementPage'
import CitationAnalysisPage from './pages/CitationAnalysisPage'
import ReportGenerationPage from './pages/ReportGenerationPage'
import { isAuthenticated, clearUser, getStoredUser } from './services/auth'
import './App.css'

const { Header, Content } = Layout

function App() {
  const [isAuthed, setIsAuthed] = useState(false)
  const [isChecking, setIsChecking] = useState(true)

  // 检查登录状态
  const checkAuth = () => {
    const loggedIn = isAuthenticated()
    setIsAuthed(loggedIn)
    setIsChecking(false)
  }

  useEffect(() => {
    // 初始检查登录状态
    checkAuth()

    // 监听自定义登录事件
    const handleLogin = () => {
      checkAuth()
    }
    window.addEventListener('userLogin', handleLogin)
    window.addEventListener('userLogout', handleLogin)

    return () => {
      window.removeEventListener('userLogin', handleLogin)
      window.removeEventListener('userLogout', handleLogin)
    }
  }, [])

  // 受保护的路由组件
  const ProtectedRoute = ({ children }) => {
    if (isChecking) {
      return (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
          <Spin size="large" />
        </div>
      )
    }
    return isAuthed ? children : <Navigate to="/" replace />
  }

  const AppShell = () => {
    const location = useLocation()
    const navigate = useNavigate()
    const username = getStoredUser()?.username || '用户'
    const showTopNav = isAuthed && location.pathname !== '/'
    const selectedNavKey = location.pathname.startsWith('/reports') ? 'reports' : 'tasks'

    const userMenuItems = [
      {
        key: 'user-info',
        label: (
          <div style={{ padding: '8px 0' }}>
            <div style={{ fontWeight: 500, marginBottom: 4 }}>用户信息</div>
            <div style={{ fontSize: '12px', color: '#999' }}>
              <div>用户名: {username}</div>
              <div style={{ marginTop: 4 }}>角色: 普通用户</div>
            </div>
          </div>
        ),
        disabled: true
      },
      { type: 'divider' },
      {
        key: 'logout',
        label: (
          <Space>
            <LogoutOutlined />
            <span>退出登录</span>
          </Space>
        ),
        danger: true,
        onClick: () => {
          clearUser()
          window.dispatchEvent(new Event('userLogout'))
          navigate('/')
        }
      }
    ]

    return (
      <Layout className="app-layout">
        {showTopNav && (
          <Header className="top-navbar">
            <div className="top-navbar-left">CiteScope 引用视界</div>
            <Menu
              mode="horizontal"
              selectedKeys={[selectedNavKey]}
              className="top-navbar-menu"
              items={[
                { key: 'tasks', label: '任务管理' },
                { key: 'reports', label: '报告管理' }
              ]}
              onClick={({ key }) => navigate(key === 'tasks' ? '/tasks' : '/reports')}
            />
            <div className="top-navbar-right">
              <Dropdown
                menu={{ items: userMenuItems }}
                trigger={['hover']}
                placement="bottomRight"
                overlayStyle={{ minWidth: '200px' }}
              >
                <div className="top-navbar-user-trigger">
                  <Avatar
                    size="small"
                    icon={<UserOutlined />}
                    style={{ backgroundColor: '#22c55e', marginRight: 8 }}
                  />
                  <span style={{ color: '#666', marginRight: 4 }}>{username}</span>
                  <DownOutlined style={{ fontSize: '12px', color: '#999' }} />
                </div>
              </Dropdown>
            </div>
          </Header>
        )}
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<LoginPage />} />
            <Route
              path="/tasks"
              element={
                <ProtectedRoute>
                  <TaskManagementPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/analysis/:taskId"
              element={
                <ProtectedRoute>
                  <CitationAnalysisPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/reports"
              element={
                <ProtectedRoute>
                  <ReportGenerationPage />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Content>
      </Layout>
    )
  }

  return (
    <Router>
      <AppShell />
    </Router>
  )
}

export default App


