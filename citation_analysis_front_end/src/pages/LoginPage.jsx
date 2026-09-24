import React, { useEffect, useState } from 'react'
import { Form, Input, Button, Card, Typography, message, Tabs } from 'antd'
import { UserOutlined, LockOutlined, LoginOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { isAuthenticated, loginUser, registerUser, setAuthData } from '../services/auth'
import './LoginPage.css'

const { Title, Text } = Typography

function LoginPage() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState('login')

  useEffect(() => {
    if (isAuthenticated()) {
      navigate('/tasks')
    }
  }, [navigate])

  useEffect(() => {
    form.resetFields()
  }, [form, mode])

  const handleLogin = async (values) => {
    setLoading(true)
    try {
      const nickname = values.username?.trim()
      const password = values.password?.trim()
      if (!nickname || !password) {
        message.error('请输入用户名和密码')
        return
      }

      if (mode === 'login') {
        const { ok, result } = await loginUser({ nickname, password })
        if (!ok || !result?.success) {
          message.error(result?.message || '登录失败')
          return
        }
        const token = result?.data?.token || ''
        const user = result?.data?.user || { username: nickname }
        setAuthData({ token, user })
        message.success('登录成功！')
        window.dispatchEvent(new Event('userLogin'))
        navigate('/tasks')
        return
      }

      const email = values.email?.trim() || ''
      const { ok, result } = await registerUser({ nickname, password, email })
      if (!ok || !result?.success) {
        message.error(result?.message || '注册失败')
        return
      }
      message.success('注册成功，请登录')
      setMode('login')
      form.setFieldsValue({ username: nickname, password: '' })
    } catch (error) {
      console.error('登录/注册失败:', error)
      message.error('请求失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <Card className="login-card" bordered={false}>
          <div className="login-header">
            <Title level={2} className="login-title">
              CiteScope 引用视界
            </Title>
            <Text type="secondary" className="login-subtitle">
              基于多智能体的学术论文引用分析与影响力评估平台
            </Text>
          </div>

          <Form
            form={form}
            name="login"
            onFinish={handleLogin}
            autoComplete="off"
            size="large"
            className="login-form"
          >
            <Tabs
              activeKey={mode}
              onChange={setMode}
              items={[
                { key: 'login', label: '登录' },
                { key: 'register', label: '注册' }
              ]}
            />
            <Form.Item
              name="username"
              rules={[
                { required: true, message: '请输入用户名' },
                { min: 3, message: '用户名至少3个字符' },
                { max: 20, message: '用户名最多20个字符' },
                { pattern: /^[a-zA-Z0-9_]+$/, message: '仅支持字母、数字和下划线' }
              ]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="用户名"
                autoComplete="username"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 8, message: '密码至少8个字符' },
                { pattern: /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?`~]+$/, message: '需包含字母和数字' }
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="密码"
                autoComplete="current-password"
              />
            </Form.Item>

            {mode === 'register' && (
              <>
                <Form.Item
                  name="confirmPassword"
                  dependencies={['password']}
                  rules={[
                    { required: true, message: '请再次输入密码' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (!value || getFieldValue('password') === value) {
                          return Promise.resolve()
                        }
                        return Promise.reject(new Error('两次输入的密码不一致'))
                      }
                    })
                  ]}
                >
                  <Input.Password
                    prefix={<LockOutlined />}
                    placeholder="确认密码"
                    autoComplete="new-password"
                  />
                </Form.Item>
                <Form.Item name="email" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
                  <Input placeholder="邮箱（可选）" autoComplete="email" />
                </Form.Item>
              </>
            )}

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                block
                icon={<LoginOutlined />}
                loading={loading}
                className="login-button"
              >
                {mode === 'login' ? '登录' : '注册'}
              </Button>
            </Form.Item>
          </Form>

          <div className="login-footer">
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {mode === 'login'
                ? '提示：请使用已注册账号登录'
                : '提示：注册需填写昵称、密码，可选邮箱'}
            </Text>
          </div>
        </Card>
      </div>
    </div>
  )
}

export default LoginPage
