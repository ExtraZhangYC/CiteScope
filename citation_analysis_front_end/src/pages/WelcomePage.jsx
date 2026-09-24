import React from 'react'
import { Button, Card, Typography, Space, Row, Col } from 'antd'
import { ArrowRightOutlined, FileTextOutlined, BarChartOutlined, TeamOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import './WelcomePage.css'

const { Title, Paragraph } = Typography

function WelcomePage() {
  const navigate = useNavigate()

  const features = [
    {
      icon: <FileTextOutlined style={{ fontSize: '48px', color: '#22c55e' }} />,
      title: '智能学术检索',
      description: '自动从多个学术数据库检索论文，下载并提取文本内容'
    },
    {
      icon: <BarChartOutlined style={{ fontSize: '48px', color: '#52c41a' }} />,
      title: '引用分析',
      description: '深度分析论文的引用情况，包括引用量、情感倾向和影响力评估'
    },
    {
      icon: <TeamOutlined style={{ fontSize: '48px', color: '#faad14' }} />,
      title: '多智能体协作',
      description: '基于多智能体系统，实现高效的论文分析和处理流程'
    }
  ]

  return (
    <div className="welcome-page">
      <div className="welcome-hero">
        <Title level={1} className="welcome-title">
          CiteScope 引用视界
        </Title>
        <Paragraph className="welcome-subtitle">
          基于多智能体的学术论文引用分析与影响力评估平台
        </Paragraph>
        <Button
          type="primary"
          size="large"
          icon={<ArrowRightOutlined />}
          onClick={() => navigate('/tasks')}
          className="welcome-cta-button"
        >
          开始使用
        </Button>
      </div>

      <div className="welcome-features">
        <Title level={2} className="features-title">
          核心功能
        </Title>
        <Row gutter={[24, 24]} justify="center">
          {features.map((feature, index) => (
            <Col xs={24} sm={12} lg={8} key={index}>
              <Card className="feature-card" hoverable>
                <Space direction="vertical" align="center" size="large" style={{ width: '100%' }}>
                  {feature.icon}
                  <Title level={4}>{feature.title}</Title>
                  <Paragraph style={{ textAlign: 'center', color: '#666' }}>
                    {feature.description}
                  </Paragraph>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      <div className="welcome-info">
        <Card>
          <Title level={3}>系统特点</Title>
          <ul className="info-list">
            <li>支持批量论文分析，以任务为单位进行管理</li>
            <li>自动识别引文的情感倾向（支持/中立/反对）</li>
            <li>提供详细的引用分析报告和学术影响力评估</li>
            <li>直观的可视化界面，便于查看和分析结果</li>
          </ul>
        </Card>
      </div>
    </div>
  )
}

export default WelcomePage


