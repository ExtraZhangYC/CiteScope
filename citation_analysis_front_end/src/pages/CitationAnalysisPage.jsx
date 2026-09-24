import React, { useState, useEffect, useRef } from 'react'
import {
  Card,
  Input,
  Button,
  Table,
  Typography,
  Space,
  Tag,
  Modal,
  Spin,
  Descriptions,
  Divider,
  Alert,
  Row,
  Col,
  Statistic,
  message,
  Progress,
} from 'antd'
import {
  SearchOutlined,
  ArrowLeftOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  MinusCircleOutlined,
  DatabaseOutlined,
  EyeOutlined,
  HeartOutlined,
  UploadOutlined
} from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../services/apiClient'
import './CitationAnalysisPage.css'

const { Title, Paragraph, Text } = Typography
const { TextArea } = Input

function CitationAnalysisPage() {
  const navigate = useNavigate()
  const { taskId } = useParams() // taskId 现在实际上是 paperId
  const [paperInput, setPaperInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState('')
  const [uploadingCitationId, setUploadingCitationId] = useState(null)
  const [analysisData, setAnalysisData] = useState(null)
  const [selectedCitation, setSelectedCitation] = useState(null)
  const [modalVisible, setModalVisible] = useState(false)
  const [taskName, setTaskName] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [citationMeta, setCitationMeta] = useState({})
  const [paperAuthors, setPaperAuthors] = useState([])
  const [paperCitationNumber, setPaperCitationNumber] = useState(null)
  const [paperCitationSnapshotTime, setPaperCitationSnapshotTime] = useState('')
  const [paperLink, setPaperLink] = useState('')

  // API基础URL（直接访问后端）
  const API_BASE_URL = '/api'
  const CITATION_API_BASE_URL = '/api'
  const [paperId, setPaperId] = useState(null)
  const pollIntervalRef = useRef(null) // 用于存储轮询 interval ID

  // 通过 paper_id 获取论文信息
  const loadPaperInfo = async (id) => {
    try {
      const response = await apiFetch(`${API_BASE_URL}/papers/${id}`)
      const result = await response.json()
      if (result.success && result.data) {
        const paper = result.data
        setTaskName(paper.title || '')
        setPaperInput(paper.title || '')
        const authors = Array.isArray(paper.authors)
          ? paper.authors.filter(Boolean)
          : (typeof paper.authors === 'string' && paper.authors.trim()
            ? (() => {
                try {
                  const parsed = JSON.parse(paper.authors)
                  return Array.isArray(parsed) ? parsed.filter(Boolean) : [paper.authors]
                } catch {
                  return paper.authors.split(',').map((a) => a.trim()).filter(Boolean)
                }
              })()
            : [])
        setPaperAuthors(authors)
        const citationNumber = paper.citation_number ?? paper.citationCount ?? paper.citation_count
        setPaperCitationNumber(
          citationNumber != null && citationNumber !== '' ? Number(citationNumber) : null
        )
        setPaperCitationSnapshotTime(
          new Date().toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' })
        )
        setPaperLink((paper.link || '').trim())
        return paper
      }
    } catch (error) {
      console.error('加载论文信息失败:', error)
    }
    setPaperAuthors([])
    setPaperCitationNumber(null)
    setPaperCitationSnapshotTime('')
    setPaperLink('')
    return null
  }

  const loadCitationLinks = async (id) => {
    try {
      const response = await apiFetch(`${CITATION_API_BASE_URL}/papers/${id}/citations`)
      const result = await response.json()
      if (result.success && result.data && Array.isArray(result.data.citations)) {
        const metaMap = {}
        result.data.citations.forEach((citation) => {
          const title = citation?.title
          const link = citation?.download_link || ''
          const authors = Array.isArray(citation?.authors)
            ? citation.authors.filter(Boolean)
            : []
          const venue = citation?.venue || ''
          const citeByTotal = citation?.cite_by_total
          if (title && !metaMap[title]) {
            metaMap[title] = { link, authors, venue, citeByTotal }
          }
        })
        setCitationMeta(metaMap)
      }
    } catch (error) {
      console.error('加载引文链接失败:', error)
    }
  }

  // 从后端加载论文信息和分析结果
  useEffect(() => {
    if (taskId) {
      // taskId 现在就是 paperId（从 TaskManagementPage 传递过来的）
      const id = parseInt(taskId)
      if (!isNaN(id)) {
        setPaperId(id)
        // 加载论文信息
        loadPaperInfo(id).then(() => {
          // 加载分析结果
          loadSavedAnalysis(id)
          // 加载引文链接
          loadCitationLinks(id)
        })
      } else {
        message.error('无效的论文ID')
      }
    }
    
    // 组件卸载时清理轮询
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [taskId])

  // 更新任务的引文数量（不再使用localStorage，数据由后端管理）

  // 从后端加载已保存的分析结果
  const loadSavedAnalysis = async (paperIdParam = null) => {
    try {
      const id = paperIdParam || paperId
      if (!id) {
        console.warn('paper_id 不存在，无法加载分析结果')
        return
      }

      const response = await apiFetch(`${API_BASE_URL}/analysis/${id}`)
      const result = await response.json()
      
      if (result.success && result.data) {
        // 后端返回格式: { paper_id, analysis: [...] }
        const analysisList = result.data.analysis || []
        
        // 从analysis中提取overview（直接查找包含overview字段的对象）
        let extractedOverview = null
        if (analysisList.length > 0) {
          // 策略1: 优先查找包含overview字段的对象
          let overviewItem = analysisList.find(item => item && item.overview)
          
          // 策略2: 如果没找到，尝试找id最大的对象（向后兼容）
          if (!overviewItem) {
            overviewItem = analysisList.reduce((max, item) => {
              if (!max) return item
              const itemId = typeof item.id === 'string' ? parseInt(item.id) || 0 : (item.id || 0)
              const maxId = typeof max.id === 'string' ? parseInt(max.id) || 0 : (max.id || 0)
              return itemId > maxId ? item : max
            }, analysisList[0])
          }
          
          if (overviewItem && overviewItem.overview) {
            extractedOverview = {
              original_paper: overviewItem.original_paper || '',
              overview: overviewItem.overview
            }
          }
        }
        
        // 过滤掉overview对象，只保留有paper字段的条目
        const citations = analysisList.filter(item => item && item.paper && !item.overview)
        
        setAnalysisData({
          overview: extractedOverview,
          citations: citations
        })
      } else {
        // 分析结果不存在或加载失败
        if (result.code === 404) {
          // 404 表示分析结果不存在，这是正常的，不需要显示错误
          console.log('分析结果尚未生成，请先进行分析')
          setAnalysisData(null)
        } else {
          message.warning(result.message || '加载分析结果失败')
        }
      }
    } catch (error) {
      console.error('加载已保存数据失败:', error)
      message.error('加载分析结果失败，请检查后端服务是否正常运行')
    }
  }

  // 加载分析数据（从后端API）
  const loadAnalysisData = async () => {
    try {
      // 使用当前的 paperId 或从 URL 参数获取
      let id = paperId
      if (!id && taskId) {
        const parsedId = parseInt(taskId)
        if (!isNaN(parsedId)) {
          id = parsedId
          setPaperId(id)
        }
      }
      
      if (!id) {
        message.error('无法找到对应的论文ID，请先创建论文')
        return null
      }

      // 使用 GET 方法获取分析结果
      const response = await apiFetch(`${API_BASE_URL}/analysis/${id}`)
      const result = await response.json()
      
      if (result.success && result.data) {
        // 后端返回格式: { paper_id, analysis: [...] }
        const analysisList = result.data.analysis || []
        
        // 从analysis中提取overview（直接查找包含overview字段的对象）
        let extractedOverview = null
        if (analysisList.length > 0) {
          // 策略1: 优先查找包含overview字段的对象
          let overviewItem = analysisList.find(item => item && item.overview)
          
          // 策略2: 如果没找到，尝试找id最大的对象（向后兼容）
          if (!overviewItem) {
            overviewItem = analysisList.reduce((max, item) => {
              if (!max) return item
              const itemId = typeof item.id === 'string' ? parseInt(item.id) || 0 : (item.id || 0)
              const maxId = typeof max.id === 'string' ? parseInt(max.id) || 0 : (max.id || 0)
              return itemId > maxId ? item : max
            }, analysisList[0])
          }
          
          if (overviewItem && overviewItem.overview) {
            extractedOverview = {
              original_paper: overviewItem.original_paper || '',
              overview: overviewItem.overview
            }
          }
        }
        
        // 过滤掉overview对象，只保留有paper字段的条目
        const citations = analysisList.filter(item => item && item.paper && !item.overview)
        
        const analysisResult = {
          overview: extractedOverview,
          citations: citations
        }
        setAnalysisData(analysisResult)
        return analysisResult
      } else {
        message.error(result.message || result.error || '分析失败')
        return null
      }
    } catch (error) {
      console.error('加载数据失败:', error)
      message.error('加载分析数据失败，请确保后端服务正在运行')
      return null
    }
  }

  const handleSubmit = async () => {
    // 获取当前的 paperId
    let id = paperId
    if (!id && taskId) {
      const parsedId = parseInt(taskId)
      if (!isNaN(parsedId)) {
        id = parsedId
        setPaperId(id)
      }
    }
    
    if (!id) {
      message.error('无法找到对应的论文ID，请先创建论文')
      return
    }

    // 如果没有paperInput，使用taskName
    const paperName = paperInput.trim() || taskName.trim()
    if (!paperName) {
      message.warning('论文名未设置，请先返回任务列表设置论文名')
      return
    }

    setLoading(true)
    setProgress(0)
    setCurrentStep('正在启动下载和分析任务...')
    
    try {
      // 调用后端 download_analysis 接口
      const response = await apiFetch(`${API_BASE_URL}/analysis_download/${id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      })

      // 检查HTTP状态码
      if (!response.ok) {
        const errorText = await response.text()
        console.error('启动分析失败，HTTP状态码:', response.status, errorText)
        message.error(`启动分析失败: ${response.status === 404 ? '论文不存在' : response.status === 500 ? '服务器错误' : '未知错误'}`)
        setLoading(false)
        setProgress(0)
        setCurrentStep('')
        return
      }

      const result = await response.json()
      
      // 后端返回格式: { success: true, code: 200, message: "start to download paper and analysis for {paper_name}", data: null }
      if (result.success === true) {
        message.success('下载和分析任务已启动，正在后台处理中...')
        
        // 显示进度提示
        setCurrentStep('任务已启动，正在下载引用文件并进行分析...')
        setProgress(10)
        
        // 由于这是异步任务，启动轮询机制来检查分析状态
        // 每5秒检查一次分析结果
        let pollCount = 0
        const maxPollCount = 120 // 最多轮询120次（10分钟）
        
        // 清除之前的轮询（如果存在）
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
        }
        
        pollIntervalRef.current = setInterval(async () => {
          pollCount++
          
          // 更新进度（模拟进度，实际进度由后端控制）
          const simulatedProgress = Math.min(10 + (pollCount * 2), 90)
          setProgress(simulatedProgress)
          
          // 尝试加载分析结果
          try {
            const analysisResponse = await apiFetch(`${API_BASE_URL}/analysis/${id}`)
            const analysisResult = await analysisResponse.json()
            
            if (analysisResult.success && analysisResult.data && analysisResult.data.analysis) {
              // 分析完成，加载数据
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current)
                pollIntervalRef.current = null
              }
              setProgress(100)
              setCurrentStep('分析完成！')
              
              // 等待一小段时间后完成
              await new Promise(resolve => setTimeout(resolve, 500))
              
              // 加载分析数据
              await loadAnalysisData()
              
              setLoading(false)
              setProgress(0)
              setCurrentStep('')
              message.success('分析完成！')
            } else if (pollCount >= maxPollCount) {
              // 超时
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current)
                pollIntervalRef.current = null
              }
              setLoading(false)
              setProgress(0)
              setCurrentStep('')
              message.warning('分析任务仍在进行中，请稍后刷新页面查看结果')
            }
          } catch (error) {
            console.error('轮询分析结果失败:', error)
            // 继续轮询，不中断
          }
        }, 5000) // 每5秒轮询一次
      } else {
        message.error(result.message || '启动分析失败')
        setLoading(false)
        setProgress(0)
        setCurrentStep('')
      }
    } catch (error) {
      console.error('启动分析任务失败:', error)
      message.error('启动分析任务失败，请检查后端服务是否正常运行')
      setLoading(false)
      setProgress(0)
      setCurrentStep('')
    }
  }

  const handleCitationClick = (citation) => {
    setSelectedCitation(citation)
    setModalVisible(true)
  }

  const getSentimentTag = (sentiment) => {
    if (sentiment === 'positive') {
      return <Tag color="green" icon={<CheckCircleOutlined />}>支持</Tag>
    } else if (sentiment === 'negative') {
      return <Tag color="red" icon={<CloseCircleOutlined />}>反对</Tag>
    } else if (sentiment === 'irrelevant') {
      return <Tag color="default" icon={<MinusCircleOutlined />}>不相关</Tag>
    } else {
      return <Tag color="default" icon={<MinusCircleOutlined />}>中立</Tag>
    }
  }

  const getCitationStatusTag = (status) => {
    const statusMap = {
      'not_downloaded': { color: 'default', text: '未下载' },
      'not downloaded': { color: 'default', text: '未下载' },
      'downloaded': { color: 'processing', text: '分析中' },
      'analysised': { color: 'success', text: '已分析' }
    }
    const config = statusMap[status] || { color: 'default', text: status || '未知' }
    return <Tag color={config.color}>{config.text}</Tag>
  }

  const handleManualUpload = (citation, event) => {
    event?.stopPropagation()
    if (!paperId) {
      message.error('无法找到论文ID')
      return
    }
    const citationId = citation?.id
    if (!citationId) {
      message.error('无法找到引文ID')
      return
    }

    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/pdf'
    input.onchange = async () => {
      const file = input.files && input.files[0]
      if (!file) {
        return
      }
      setUploadingCitationId(citationId)
      try {
        const formData = new FormData()
        formData.append('file', file)
        const response = await apiFetch(
          `${API_BASE_URL}/papers/${paperId}/citations/${citationId}/upload`,
          {
            method: 'POST',
            body: formData
          }
        )
        if (!response.ok) {
          const errorText = await response.text()
          console.error('上传失败，HTTP状态码:', response.status, errorText)
          message.error('上传失败，请检查后端服务是否正常运行')
          return
        }
        const result = await response.json()
        if (result.success === true) {
          message.success('上传成功，开始分析')
          const analysisResponse = await apiFetch(
            `${API_BASE_URL}/single_analysis/${paperId}/${citationId}`,
            { method: 'POST' }
          )
          if (!analysisResponse.ok) {
            const errorText = await analysisResponse.text()
            console.error('启动单条分析失败，HTTP状态码:', analysisResponse.status, errorText)
            message.error('启动单条分析失败，请检查后端服务是否正常运行')
            return
          }
          await loadSavedAnalysis(paperId)
          await loadAnalysisData()
        } else {
          message.error(result.message || '上传失败')
        }
      } catch (error) {
        console.error('上传失败:', error)
        message.error('上传失败，请检查后端服务是否正常运行')
      } finally {
        setUploadingCitationId(null)
      }
    }
    input.click()
  }

  const getCitationTypeTag = (type) => {
    const typeMap = {
      'background': { color: 'blue', text: '背景引用' },
      'method': { color: 'purple', text: '方法引用' },
      'result': { color: 'orange', text: '结果引用' },
      'other': { color: 'default', text: '其他' }
    }
    const config = typeMap[type] || typeMap['other']
    return <Tag color={config.color}>{config.text}</Tag>
  }

  const getCitationModeTag = (mode) => {
    const modeMap = {
      'direct_quote': { color: 'cyan', text: '直接引用' },
      'indirect_reference': { color: 'geekblue', text: '间接引用' },
      'unknown': { color: 'default', text: '未知' }
    }
    const config = modeMap[mode] || modeMap['unknown']
    return <Tag color={config.color}>{config.text}</Tag>
  }

  // 计算引文项的正面、中立和负面引用数量
  const getCitationCounts = (item) => {
    if (!item.citations || item.citations.length === 0) {
      return { positive: 0, neutral: 0, negative: 0, irrelevant: 0 }
    }
    const positive = item.citations.filter(c => c.sentiment === 'positive').length
    const neutral = item.citations.filter(c => c.sentiment === 'neutral').length
    const negative = item.citations.filter(c => c.sentiment === 'negative').length
    const irrelevant = item.citations.filter(c => c.sentiment === 'irrelevant').length
    return { positive, neutral, negative, irrelevant }
  }

  // 过滤引文列表
  const filterCitations = (citations, keyword) => {
    if (!keyword.trim()) {
      return citations
    }
    const lowerKeyword = keyword.toLowerCase()
    return citations.filter(item => {
      // 搜索论文名称
      if (item.paper && item.paper.toLowerCase().includes(lowerKeyword)) {
        return true
      }
      // 也可以搜索引用内容中的文本
      if (item.citations && item.citations.some(c => 
        c.text && c.text.toLowerCase().includes(lowerKeyword)
      )) {
        return true
      }
      return false
    })
  }

  // 从citations中找出包含overview的对象
  const getOverviewFromCitations = (citations) => {
    if (!citations || citations.length === 0) {
      return null
    }
    // 策略1: 优先查找包含overview字段的对象
    let overviewItem = citations.find(item => item && item.overview)
    
    // 策略2: 如果没找到，尝试找id最大的对象（向后兼容）
    if (!overviewItem) {
      overviewItem = citations.reduce((max, item) => {
        if (!max) return item
        const itemId = typeof item.id === 'string' ? parseInt(item.id) || 0 : (item.id || 0)
        const maxId = typeof max.id === 'string' ? parseInt(max.id) || 0 : (max.id || 0)
        return itemId > maxId ? item : max
      }, citations[0])
    }
    
    // 如果该对象有overview字段，返回它
    if (overviewItem && overviewItem.overview) {
      return {
        original_paper: overviewItem.original_paper || '',
        overview: overviewItem.overview
      }
    }
    return null
  }

  // 获取overview，优先从citations中提取，否则使用analysisData中的overview
  const extractedOverview = getOverviewFromCitations(analysisData?.citations)
  let overview = null
  
  if (extractedOverview && extractedOverview.overview) {
    overview = extractedOverview
  } else if (analysisData?.overview) {
    if (typeof analysisData.overview === 'string') {
      overview = { original_paper: '', overview: analysisData.overview }
    } else if (analysisData.overview && analysisData.overview.overview) {
      overview = {
        original_paper: analysisData.overview.original_paper || '',
        overview: analysisData.overview.overview
      }
    } else if (analysisData.overview && typeof analysisData.overview === 'object') {
      // 如果overview是一个对象但没有overview字段，可能是旧格式
      overview = {
        original_paper: analysisData.overview.original_paper || '',
        overview: ''
      }
    }
  }
  
  // 调试信息（开发时使用）
  if (process.env.NODE_ENV === 'development') {
    console.log('Overview data:', { overview, extractedOverview, analysisDataOverview: analysisData?.overview })
  }
  const citations = (analysisData?.citations || []).filter(item => item.paper && !item.overview) // 过滤掉overview对象
  const filteredCitations = filterCitations(citations, searchKeyword)

  const citationColumns = [
    {
      title: '论文名称',
      dataIndex: 'paper',
      key: 'paper',
      width: '28%',
      sorter: (a, b) => String(a.paper || '').localeCompare(String(b.paper || ''), 'zh-CN')
    },
    {
      title: '作者',
      key: 'authors',
      width: '20%',
      render: (_, item) => {
        const authors = citationMeta[item.paper]?.authors || []
        return authors.length > 0 ? authors.join(', ') : '-'
      },
      sorter: (a, b) => {
        const authorsA = (citationMeta[a.paper]?.authors || []).join(', ')
        const authorsB = (citationMeta[b.paper]?.authors || []).join(', ')
        return authorsA.localeCompare(authorsB, 'zh-CN')
      }
    },
    {
      title: '引用量',
      key: 'citeByTotal',
      width: '10%',
      render: (_, item) => {
        const value = citationMeta[item.paper]?.citeByTotal
        return value == null ? '-' : value
      },
      sorter: (a, b) => {
        const valueA = citationMeta[a.paper]?.citeByTotal
        const valueB = citationMeta[b.paper]?.citeByTotal
        const numA = typeof valueA === 'number' ? valueA : Number(valueA)
        const numB = typeof valueB === 'number' ? valueB : Number(valueB)
        const normalizedA = Number.isFinite(numA) ? numA : -1
        const normalizedB = Number.isFinite(numB) ? numB : -1
        return normalizedA - normalizedB
      }
    },
    {
      title: '正面评价',
      key: 'positiveCount',
      width: '10%',
      render: (_, item) => {
        const counts = getCitationCounts(item)
        return counts.positive
      },
      sorter: (a, b) => {
        const countsA = getCitationCounts(a)
        const countsB = getCitationCounts(b)
        return countsA.positive - countsB.positive
      }
    },
    {
      title: '负面评价',
      key: 'negativeCount',
      width: '10%',
      render: (_, item) => {
        const counts = getCitationCounts(item)
        return counts.negative
      },
      sorter: (a, b) => {
        const countsA = getCitationCounts(a)
        const countsB = getCitationCounts(b)
        return countsA.negative - countsB.negative
      }
    },
    {
      title: '中立/无关评价',
      key: 'neutralIrrelevantCount',
      width: '13%',
      render: (_, item) => {
        const counts = getCitationCounts(item)
        return counts.neutral + counts.irrelevant
      },
      sorter: (a, b) => {
        const countsA = getCitationCounts(a)
        const countsB = getCitationCounts(b)
        return (countsA.neutral + countsA.irrelevant) - (countsB.neutral + countsB.irrelevant)
      }
    },
    {
      title: '状态',
      key: 'downloadStatus',
      width: '10%',
      render: (_, item) => (item.status ? getCitationStatusTag(item.status) : '-'),
      sorter: (a, b) => String(a.status || '').localeCompare(String(b.status || ''), 'zh-CN')
    },
    {
      title: '操作',
      key: 'actions',
      width: '10%',
      render: (_, item) => (
        <Space>
          {(item.status === 'not_downloaded' || item.status === 'not downloaded') && (
            <Button
              size="small"
              icon={<UploadOutlined />}
              loading={uploadingCitationId === item.id}
              onClick={(event) => handleManualUpload(item, event)}
            >
              上传PDF
            </Button>
          )}
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleCitationClick(item)}
          >
            查看
          </Button>
        </Space>
      ),
      sorter: (a, b) => {
        const actionA = (a.status === 'not_downloaded' || a.status === 'not downloaded') ? 0 : 1
        const actionB = (b.status === 'not_downloaded' || b.status === 'not downloaded') ? 0 : 1
        return actionA - actionB
      }
    }
  ]

  return (
    <div className="citation-analysis-page">
      <Card>
        <div className="page-header">
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/tasks')}
            style={{ marginBottom: 16 }}
          >
            返回任务列表
          </Button>
          <Title level={2}>引用视界 · 引用分析</Title>
        </div>

        {/* 输入区域 */}
        <Card className="input-section" title="论文信息">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <div>
              <Text strong>论文名：</Text>
              <Text>{taskName || paperInput || '未设置'}</Text>
            </div>
            <div>
              <Text strong>论文作者：</Text>
              <Text>{paperAuthors.length > 0 ? paperAuthors.join(', ') : '-'}</Text>
            </div>
            <div>
              <Text strong>
                引用量（截止到{paperCitationSnapshotTime || new Date().toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' })}）：
              </Text>
              <Text>{paperCitationNumber != null && Number.isFinite(paperCitationNumber) ? paperCitationNumber : '-'}</Text>
            </div>
            <div>
              <Text strong>论文链接：</Text>
              {paperLink ? (
                <a
                  href={paperLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ marginLeft: 4 }}
                >
                  {paperLink}
                </a>
              ) : (
                <Text>-</Text>
              )}
            </div>
          </Space>
        </Card>

        {/* 加载状态 */}
        {loading && (
          <Card>
            <div className="loading-container">
              <Spin size="large" />
              <div style={{ marginTop: 24, width: '100%', maxWidth: '600px', margin: '24px auto 0' }}>
                <Progress 
                  percent={Math.round(progress)} 
                  status="active"
                  strokeColor={{
                    '0%': '#22c55e',
                    '100%': '#15803d',
                  }}
                  showInfo={true}
                />
              </div>
              <Paragraph style={{ marginTop: 24, textAlign: 'center', fontSize: '16px', fontWeight: 500 }}>
                {currentStep || '正在处理中...'}
              </Paragraph>
              <Paragraph style={{ marginTop: 8, textAlign: 'center', color: '#999' }}>
                预计剩余时间: {Math.max(0, Math.ceil((100 - progress) * 0.14))} 秒
              </Paragraph>
            </div>
          </Card>
        )}

        {/* 引用分析概述 */}
        {overview && overview.overview && overview.overview.trim() && !loading && (
          <Card className="overview-section" title="引用分析概述">
            {overview.original_paper && (
              <div style={{ marginBottom: 16 }}>
                <Text strong>被引用论文：</Text>
                <Text>{overview.original_paper}</Text>
              </div>
            )}
            <Paragraph style={{ whiteSpace: 'pre-wrap', fontSize: '14px', lineHeight: '1.8' }}>
              {overview.overview}
            </Paragraph>
          </Card>
        )}

        {/* 引文列表 */}
        {citations.length > 0 && !loading && (
          <Card 
            className="citations-section" 
            title={
              <span>引文列表 ({filteredCitations.length}/{citations.length}篇)</span>
            }
          >
            <div style={{ marginBottom: 16 }}>
              <Input
                placeholder="搜索引文（支持搜索论文名称和引用内容）"
                prefix={<SearchOutlined />}
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
                allowClear
                style={{ width: '100%' }}
              />
            </div>
            <Table
              rowKey={(item) => `${item.id}-${item.paper}`}
              columns={citationColumns}
              dataSource={filteredCitations}
              showSorterTooltip={false}
              pagination={{ pageSize: 10 }}
              onRow={(item) => ({
                onDoubleClick: () => handleCitationClick(item)
              })}
            />
          </Card>
        )}
      </Card>

      {/* 引文详情模态框 */}
      <Modal
        title="引文详细信息"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={900}
      >
        {selectedCitation && (
          <div>
            <Title level={4}>{selectedCitation.paper}</Title>
            {citationMeta[selectedCitation.paper]?.link && (
              <Text type="secondary">
                论文链接：
                <a
                  href={citationMeta[selectedCitation.paper].link}
                  target="_blank"
                  rel="noreferrer"
                  style={{ marginLeft: 6 }}
                >
                  {citationMeta[selectedCitation.paper].link}
                </a>
              </Text>
            )}
            {(citationMeta[selectedCitation.paper]?.authors?.length > 0 || citationMeta[selectedCitation.paper]?.venue) && (
              <div>
                <Text type="secondary">
                  {citationMeta[selectedCitation.paper]?.authors?.length > 0 && (
                    <>作者：{citationMeta[selectedCitation.paper].authors.join(', ')}</>
                  )}
                  {citationMeta[selectedCitation.paper]?.authors?.length > 0 && citationMeta[selectedCitation.paper]?.venue && ' · '}
                  {citationMeta[selectedCitation.paper]?.venue && (
                    <>论文来源：{citationMeta[selectedCitation.paper].venue}</>
                  )}
                </Text>
              </div>
            )}
            <Divider />
            
            {selectedCitation.citations && selectedCitation.citations.map((citation, index) => (
              <Card key={index} style={{ marginBottom: 16 }}>
                <Descriptions column={2} bordered size="small">
                  <Descriptions.Item
                    label="引用编号"
                    labelStyle={{ padding: '4px 8px' }}
                    contentStyle={{ padding: '4px 8px' }}
                  >
                    <Text style={{ fontSize: 12 }}>{citation.reference_number || '-'}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item
                    label="情感倾向"
                    labelStyle={{ padding: '4px 8px' }}
                    contentStyle={{ padding: '4px 8px' }}
                  >
                    <span style={{ fontSize: 12 }}>
                      {getSentimentTag(citation.sentiment)}
                      {citation.positive !== null && (
                        <Text style={{ marginLeft: 8, fontSize: 12 }}>
                          {citation.positive ? '正面' : '非正面'}
                        </Text>
                      )}
                    </span>
                  </Descriptions.Item>
                  <Descriptions.Item label="引用文本" span={2}>
                    <Paragraph
                      ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                      style={{ marginBottom: 0 }}
                    >
                      {citation.text}
                    </Paragraph>
                  </Descriptions.Item>
                  {citation.analysis && (
                    <Descriptions.Item label="详细分析" span={2}>
                      {citation.analysis}
                    </Descriptions.Item>
                  )}
                </Descriptions>
              </Card>
            ))}

            {selectedCitation.errors && selectedCitation.errors.length > 0 && (
              <Alert
                message="错误信息"
                description={
                  <ul>
                    {selectedCitation.errors.map((error, idx) => (
                      <li key={idx}>{error}</li>
                    ))}
                  </ul>
                }
                type="warning"
              />
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}

export default CitationAnalysisPage


