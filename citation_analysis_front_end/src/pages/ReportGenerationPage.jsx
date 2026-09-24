import React, { useState, useEffect } from 'react'
import {
  Button,
  Card,
  Table,
  message,
  Space,
  Typography,
  Tag,
  Spin,
  Input,
  Modal,
  Popconfirm
} from 'antd'
import {
  PlusOutlined,
  FileTextOutlined,
  DownloadOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SearchOutlined,
  EyeOutlined
} from '@ant-design/icons'
import { useLocation } from 'react-router-dom'
import { apiFetch } from '../services/apiClient'
import './ReportGenerationPage.css'

const { Title } = Typography

const API_BASE_URL = '/api'

const REPORT_STATUS_MAP = {
  pending: { color: 'default', text: '待处理' },
  analysis: { color: 'processing', text: '生成中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' }
}

function ReportGenerationPage() {
  const location = useLocation()
  const [papers, setPapers] = useState([])
  const [loadingPapers, setLoadingPapers] = useState(false)
  const [reports, setReports] = useState([])
  const [loadingReports, setLoadingReports] = useState(false)
  const [selectedPaperIds, setSelectedPaperIds] = useState([])
  const [creating, setCreating] = useState(false)
  const [paperSearchKeyword, setPaperSearchKeyword] = useState('')
  const [reportCreateModalVisible, setReportCreateModalVisible] = useState(false)
  const [reportNameModalVisible, setReportNameModalVisible] = useState(false)
  const [reportNameInput, setReportNameInput] = useState('')
  const [reportSearchKeyword, setReportSearchKeyword] = useState('')

  const preSelectedPaperIds = location.state?.paperIds || []

  const extractAuthors = (authors) => {
    if (authors == null || authors === '') return []
    if (Array.isArray(authors)) {
      return authors.filter(Boolean).map((a) => String(a))
    }
    if (typeof authors === 'string') {
      try {
        const parsed = JSON.parse(authors)
        if (Array.isArray(parsed)) {
          return parsed.filter(Boolean).map((a) => String(a))
        }
      } catch {
        // ignore parse error and fallback to plain string split
      }
      return authors
        .split(',')
        .map((a) => a.trim())
        .filter(Boolean)
    }
    return []
  }

  const highlightMatchedText = (text, keyword) => {
    const source = String(text || '')
    const key = String(keyword || '').trim()
    if (!key) return source

    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const regex = new RegExp(`(${escaped})`, 'ig')
    const parts = source.split(regex)

    return parts.map((part, index) => {
      const isMatch = new RegExp(`^${escaped}$`, 'i').test(part)
      return isMatch ? (
        <mark
          key={`${part}-${index}`}
          style={{ backgroundColor: '#fff3bf', padding: 0 }}
        >
          {part}
        </mark>
      ) : (
        <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>
      )
    })
  }

  const filteredPapers = paperSearchKeyword.trim()
    ? papers.filter((p) => {
        const keyword = paperSearchKeyword.trim().toLowerCase()
        const titleMatched = p.title && p.title.toLowerCase().includes(keyword)
        const authorsMatched = extractAuthors(p.authors).some((author) =>
          author.toLowerCase().includes(keyword)
        )
        return titleMatched || authorsMatched
      })
    : papers

  const filteredReports = reportSearchKeyword.trim()
    ? reports.filter((r) => r.name && r.name.toLowerCase().includes(reportSearchKeyword.trim().toLowerCase()))
    : reports

  const loadPapers = async () => {
    setLoadingPapers(true)
    try {
      const response = await apiFetch(`${API_BASE_URL}/papers`)
      const result = await response.json()
      if (result.success && result.data && Array.isArray(result.data)) {
        const completedPapers = result.data.filter(
          (paper) => String(paper.analysis_status || '').toUpperCase() === 'COMPLETED'
        )
        setPapers(completedPapers)
        if (preSelectedPaperIds.length > 0) {
          const ids = completedPapers
            .filter((p) => preSelectedPaperIds.some((pid) => p.id === pid || p.id === Number(pid)))
            .map((p) => p.id)
          setSelectedPaperIds(ids)
        }
      } else {
        setPapers([])
      }
    } catch (error) {
      console.error('加载论文列表失败:', error)
      message.error('加载论文列表失败')
      setPapers([])
    } finally {
      setLoadingPapers(false)
    }
  }

  const loadReports = async () => {
    setLoadingReports(true)
    try {
      const response = await apiFetch(`${API_BASE_URL}/reports`)
      const result = await response.json()
      if (result.success && result.data && Array.isArray(result.data)) {
        setReports(result.data)
      } else {
        setReports([])
      }
    } catch (error) {
      console.error('加载报告列表失败:', error)
      message.error('加载报告列表失败')
      setReports([])
    } finally {
      setLoadingReports(false)
    }
  }

  useEffect(() => {
    loadPapers()
    loadReports()
  }, [])

  useEffect(() => {
    if (preSelectedPaperIds.length > 0 && papers.length > 0 && selectedPaperIds.length === 0) {
      const ids = papers
        .filter((p) => preSelectedPaperIds.some((pid) => p.id === pid || p.id === Number(pid)))
        .map((p) => p.id)
      if (ids.length > 0) setSelectedPaperIds(ids)
    }
  }, [papers, preSelectedPaperIds])

  const hasGenerating = reports.some((r) => r.status === 'analysis' || r.status === 'pending')
  useEffect(() => {
    if (!hasGenerating) return
    const timer = setInterval(loadReports, 3000)
    return () => clearInterval(timer)
  }, [hasGenerating])

  const handleCreateReport = async (name) => {
    if (selectedPaperIds.length === 0) {
      message.warning('请至少选择一篇论文')
      return
    }
    setCreating(true)
    try {
      const paperIds = selectedPaperIds.map(Number)
      const reportName = name != null ? String(name).trim() : ''
      const body = reportName ? { name: reportName, paper_ids: paperIds } : { paper_ids: paperIds }
      const response = await apiFetch(`${API_BASE_URL}/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      const result = await response.json()
      if (result.success && result.data) {
        message.success(`报告任务已创建：${result.data.name || result.data.report_id}`)
        setSelectedPaperIds([])
        setReportNameModalVisible(false)
        setReportNameInput('')
        await loadReports()
      } else {
        message.error(result.message || '创建报告失败')
      }
    } catch (error) {
      console.error('创建报告失败:', error)
      message.error('创建报告失败，请检查后端服务')
    } finally {
      setCreating(false)
    }
  }

  const handleOpenReportNameModal = () => {
    if (selectedPaperIds.length === 0) {
      message.warning('请至少选择一篇论文')
      return
    }
    setReportNameInput('')
    setReportCreateModalVisible(false)
    setReportNameModalVisible(true)
  }

  const handleReportNameModalOk = () => {
    const name = reportNameInput.trim()
    if (!name) {
      message.warning('请输入报告名称')
      return
    }
    handleCreateReport(name)
  }

  const sanitizeDownloadFilename = (name) => {
    if (!name || typeof name !== 'string') return ''
    return name.replace(/[/\\:*?"<>|]/g, '_').trim() || ''
  }

  const handleDownload = async (reportId, format, reportName) => {
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/reports/${reportId}/download?format=${format}`
      )
      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        message.error(err.message || '下载失败')
        return
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)

      if (format === 'html') {
        window.open(url, '_blank', 'noopener,noreferrer')
        message.success('已在新窗口打开报告')
        setTimeout(() => URL.revokeObjectURL(url), 60000)
        return
      }

      const a = document.createElement('a')
      a.href = url
      const baseName = sanitizeDownloadFilename(reportName) || `report_${reportId}`
      a.download = `${baseName}.${format}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      message.success('下载已开始')
    } catch (error) {
      console.error('下载失败:', error)
      message.error('下载失败')
    }
  }

  const handleDeleteReport = async (reportId) => {
    try {
      const response = await apiFetch(`${API_BASE_URL}/reports/${reportId}`, {
        method: 'DELETE'
      })
      if (!response.ok) {
        if (response.status === 404) {
          message.error('当前后端未提供删除报告接口或报告不存在')
          return
        }
        const err = await response.json().catch(() => ({}))
        message.error(err.message || '删除报告失败')
        return
      }
      const result = await response.json().catch(() => ({}))
      if (result.success === false) {
        message.error(result.message || '删除报告失败')
        return
      }
      message.success('报告删除成功')
      await loadReports()
    } catch (error) {
      console.error('删除报告失败:', error)
      message.error('删除报告失败')
    }
  }

  const paperColumns = [
    {
      title: '论文标题',
      dataIndex: 'title',
      width: '45%',
      ellipsis: true
    },
    {
      title: '作者',
      dataIndex: 'authors',
      width: '45%',
      ellipsis: true,
      render: (authors) => {
        const authorList = extractAuthors(authors)
        if (authorList.length === 0) return '-'

        const keyword = paperSearchKeyword.trim()
        if (!keyword) {
          return authorList.join(', ')
        }

        return (
          <>
            {authorList.map((author, index) => (
              <React.Fragment key={`${author}-${index}`}>
                {index > 0 ? ', ' : ''}
                {highlightMatchedText(author, keyword)}
              </React.Fragment>
            ))}
          </>
        )
      }
    },
    {
      title: '论文分析状态',
      dataIndex: 'analysis_status',
      width: '10%',
      render: (status) => {
        const s = (status || '').toUpperCase()
        const map = {
          CREATED: { color: 'default', text: '已创建' },
          DOWNLOADING: { color: 'processing', text: '下载中' },
          DOWNLOADED: { color: 'blue', text: '已下载' },
          ANALYZING: { color: 'processing', text: '分析中' },
          COMPLETED: { color: 'success', text: '已完成' },
          ERROR: { color: 'error', text: '错误' }
        }
        const c = map[s] || { color: 'default', text: status || '-' }
        return <Tag color={c.color}>{c.text}</Tag>
      }
    }
  ]

  const reportColumns = [
    {
      title: '报告名称',
      dataIndex: 'name',
      width: '32%',
      ellipsis: true
    },
    {
      title: '论文数',
      dataIndex: 'paper_count',
      width: '10%',
      render: (n) => n ?? '-'
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: '23%',
      render: (t) => (t ? new Date(t).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-')
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: '12%',
      render: (status) => {
        const c = REPORT_STATUS_MAP[status] || { color: 'default', text: status || '-' }
        return <Tag color={c.color}>{c.text}</Tag>
      }
    },
    {
      title: '操作',
      key: 'actions',
      width: '23%',
      render: (_, record) => {
        const canDownload = record.status === 'completed'
        return (
          <Space>
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              disabled={!canDownload}
              onClick={() => handleDownload(record.id, 'html', record.name)}
            >
              查看
            </Button>
            <Button
              type="link"
              size="small"
              icon={<DownloadOutlined />}
              disabled={!canDownload}
              onClick={() => handleDownload(record.id, 'pdf', record.name)}
            >
              下载PDF
            </Button>
            <Popconfirm
              title="确定删除该报告吗？"
              onConfirm={() => handleDeleteReport(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
              >
                删除
              </Button>
            </Popconfirm>
          </Space>
        )
      }
    }
  ]

  return (
    <div className="report-generation-page">
      <Card>
        <div className="page-header">
          <div className="header-content">
            <Title level={2}>报告管理</Title>
          </div>
        </div>

        {preSelectedPaperIds.length > 0 && (
          <div style={{ marginBottom: 16, padding: 12, background: '#f0fdf4', borderRadius: 8 }}>
            <span>已从任务管理页带入 {preSelectedPaperIds.length} 篇论文，可点击“新建报告”继续创建联合报告。</span>
          </div>
        )}

        <Modal
          title="新建报告"
          open={reportCreateModalVisible}
          onOk={handleOpenReportNameModal}
          onCancel={() => setReportCreateModalVisible(false)}
          okText="下一步"
          cancelText="取消"
          width={960}
          destroyOnClose
        >
          <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
            <Input
              placeholder="搜索论文标题或作者"
              prefix={<SearchOutlined />}
              value={paperSearchKeyword}
              onChange={(e) => setPaperSearchKeyword(e.target.value)}
              allowClear
              style={{ width: 260 }}
            />
            <Button icon={<ReloadOutlined />} onClick={loadPapers} loading={loadingPapers}>
              刷新论文列表
            </Button>
          </div>
          <Spin spinning={loadingPapers}>
            <Table
              rowKey="id"
              size="small"
              tableLayout="fixed"
              columns={paperColumns}
              dataSource={filteredPapers}
              rowSelection={{
                selectedRowKeys: selectedPaperIds,
                onChange: (keys) => {
                  const idsInFiltered = filteredPapers.map((p) => p.id)
                  const preserved = selectedPaperIds.filter((id) => !idsInFiltered.includes(id))
                  setSelectedPaperIds([...preserved, ...keys])
                }
              }}
              pagination={{ pageSize: 10 }}
            />
          </Spin>
          <div style={{ marginTop: 8, color: '#999' }}>已选 {selectedPaperIds.length} 篇</div>
        </Modal>

        <Modal
          title="输入报告名称"
          open={reportNameModalVisible}
          onOk={handleReportNameModalOk}
          onCancel={() => { setReportNameModalVisible(false); setReportNameInput('') }}
          confirmLoading={creating}
          destroyOnClose
          okText="确定"
          cancelText="取消"
        >
          <div style={{ marginBottom: 8 }}>报告名称：</div>
          <Input
            placeholder="请输入报告名称"
            value={reportNameInput}
            onChange={(e) => setReportNameInput(e.target.value)}
            onPressEnter={handleReportNameModalOk}
            allowClear
            maxLength={200}
          />
        </Modal>

        <Card title="已生成报告" size="small">
          <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
            <Input
              placeholder="搜索报告名称"
              prefix={<SearchOutlined />}
              value={reportSearchKeyword}
              onChange={(e) => setReportSearchKeyword(e.target.value)}
              allowClear
              style={{ width: 260 }}
            />
            <Space>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                size="large"
                onClick={() => setReportCreateModalVisible(true)}
              >
                新建报告
              </Button>
              <Button icon={<ReloadOutlined />} onClick={loadReports} loading={loadingReports}>
                刷新报告列表
              </Button>
            </Space>
          </div>
          <Spin spinning={loadingReports}>
            <Table
              rowKey="id"
              size="small"
              tableLayout="fixed"
              columns={reportColumns}
              dataSource={filteredReports}
              pagination={{ pageSize: 10 }}
            />
          </Spin>
        </Card>
      </Card>
    </div>
  )
}

export default ReportGenerationPage
