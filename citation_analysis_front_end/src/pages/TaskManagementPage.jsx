import React, { useState, useEffect, useRef } from 'react'
import { 
  Button, 
  Table, 
  Modal, 
  Form, 
  Input, 
  message, 
  Space, 
  Typography,
  Card,
  Popconfirm,
  Tooltip,
  Tag,
  Checkbox,
  Radio,
  Dropdown
} from 'antd'
import { PlusOutlined, DeleteOutlined, ArrowLeftOutlined, SearchOutlined, UploadOutlined, PlayCircleOutlined, EyeOutlined, DownOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../services/apiClient'
import './TaskManagementPage.css'

const { Title } = Typography

// API基础URL
const API_BASE_URL = '/api'

function TaskManagementPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState([])
  const [isModalVisible, setIsModalVisible] = useState(false)
  const [editingTask, setEditingTask] = useState(null)
  const [form] = Form.useForm()
  const [searchKeyword, setSearchKeyword] = useState('')
  const [paperStatusMap, setPaperStatusMap] = useState({}) // 存储论文ID到状态的映射
  const previousTasksRef = useRef([]) // 用于存储之前的任务数据，避免不必要的API调用
  const [isBatchModalVisible, setIsBatchModalVisible] = useState(false)
  const [batchFile, setBatchFile] = useState(null)
  const [batchTitles, setBatchTitles] = useState([])
  const [selectedBatchTitles, setSelectedBatchTitles] = useState([])
  const [batchParseError, setBatchParseError] = useState('')
  const [isBatchUploading, setIsBatchUploading] = useState(false)
  const batchFileInputRef = useRef(null)
  const [batchMode, setBatchMode] = useState('bib')
  const [batchEntries, setBatchEntries] = useState([]) // Bib 解析出的完整条目 { title, authors, doi, url }，用于上传时传作者等信息
  const [scholarIdInput, setScholarIdInput] = useState('')
  const [isScholarLoading, setIsScholarLoading] = useState(false)
  const [batchSearchKeyword, setBatchSearchKeyword] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState([])
  const [isBatchAnalyzing, setIsBatchAnalyzing] = useState(false)
  // 模糊搜索相关状态
  const [fuzzySearchResults, setFuzzySearchResults] = useState([])
  const [isFuzzySearching, setIsFuzzySearching] = useState(false)
  const [selectedFuzzyResult, setSelectedFuzzyResult] = useState(null)
  const searchInputRef = useRef(null)

  const extractBraced = (text, start, openChar, closeChar) => {
    let depth = 0
    let i = start
    while (i < text.length) {
      const ch = text[i]
      if (ch === openChar) {
        depth += 1
      } else if (ch === closeChar) {
        depth -= 1
        if (depth === 0) {
          return [text.slice(start, i + 1), i + 1]
        }
      }
      i += 1
    }
    return [text.slice(start), text.length]
  }

  const parseFieldValue = (text, idx) => {
    while (idx < text.length && /\s/.test(text[idx])) {
      idx += 1
    }
    if (idx >= text.length) {
      return ['', idx]
    }
    if (text[idx] === '{') {
      const [raw, nextIdx] = extractBraced(text, idx, '{', '}')
      const value = raw.startsWith('{') && raw.endsWith('}')
        ? raw.slice(1, -1).trim()
        : raw.trim()
      return [value, nextIdx]
    }
    if (text[idx] === '"') {
      idx += 1
      const start = idx
      let escaped = false
      while (idx < text.length) {
        const ch = text[idx]
        if (ch === '"' && !escaped) {
          return [text.slice(start, idx).trim(), idx + 1]
        }
        escaped = ch === '\\' && !escaped
        idx += 1
      }
      return [text.slice(start).trim(), text.length]
    }
    const start = idx
    while (idx < text.length && text[idx] !== ',' && text[idx] !== '}') {
      idx += 1
    }
    return [text.slice(start, idx).trim(), idx]
  }

  const parseFields = (block) => {
    const fields = {}
    let idx = 0
    while (idx < block.length) {
      while (idx < block.length && (/\s/.test(block[idx]) || block[idx] === ',')) {
        idx += 1
      }
      if (idx >= block.length) {
        break
      }
      const match = block.slice(idx).match(/^[A-Za-z0-9_:-]+/)
      if (!match) {
        idx += 1
        continue
      }
      const key = match[0].toLowerCase()
      idx += match[0].length
      while (idx < block.length && /\s/.test(block[idx])) {
        idx += 1
      }
      if (block[idx] === '=') {
        idx += 1
      }
      const [value, nextIdx] = parseFieldValue(block, idx)
      fields[key] = value
      idx = nextIdx
    }
    return fields
  }

  const parseEntry = (text, start) => {
    let idx = start + 1
    while (idx < text.length && /\s/.test(text[idx])) {
      idx += 1
    }
    const typeMatch = text.slice(idx).match(/^[A-Za-z]+/)
    if (!typeMatch) {
      return [{}, start + 1]
    }
    idx += typeMatch[0].length
    while (idx < text.length && /\s/.test(text[idx])) {
      idx += 1
    }
    if (idx >= text.length || (text[idx] !== '{' && text[idx] !== '(')) {
      return [{}, idx]
    }
    const openIdx = idx
    const openChar = text[openIdx]
    const closeChar = openChar === '{' ? '}' : ')'
    const [block, nextIdx] = extractBraced(text, openIdx, openChar, closeChar)
    const inner = block.startsWith(openChar) ? block.slice(1, -1) : block
    const firstCommaIndex = inner.indexOf(',')
    const fieldsPart = firstCommaIndex === -1 ? '' : inner.slice(firstCommaIndex + 1)
    const fields = parseFields(fieldsPart)
    return [fields, nextIdx]
  }

  const parseBibtexTitles = (content) => {
    const entries = parseBibtexEntries(content)
    const titles = entries.map((e) => e.title)
    const seen = new Set()
    const uniqueTitles = []
    titles.forEach((title) => {
      if (title && !seen.has(title)) {
        seen.add(title)
        uniqueTitles.push(title)
      }
    })
    return uniqueTitles
  }

  // 解析 BibTex 为完整条目（含 title、authors、doi、url），用于批量创建时传给后端作者等信息
  const parseBibtexEntries = (content) => {
    const rawEntries = []
    let idx = 0
    while (idx < content.length) {
      const atIdx = content.indexOf('@', idx)
      if (atIdx === -1) break
      const [fields, nextIdx] = parseEntry(content, atIdx)
      if (fields && Object.keys(fields).length > 0) rawEntries.push(fields)
      idx = Math.max(nextIdx, atIdx + 1)
    }
    const parseAuthorToArray = (authorStr) => {
      if (!authorStr || typeof authorStr !== 'string') return []
      return authorStr
        .split(/\s+and\s+/i)
        .map((a) => a.replace(/[{}]/g, '').trim())
        .filter(Boolean)
    }
    const entries = rawEntries
      .map((fields) => {
        const title = (fields.title || '').replace(/[{}]/g, '').trim()
        if (!title) return null
        return {
          title,
          authors: parseAuthorToArray(fields.author),
          doi: (fields.doi || '').replace(/[{}]/g, '').trim() || undefined,
          url: (fields.url || '').replace(/[{}]/g, '').trim() || undefined
        }
      })
      .filter(Boolean)
    const seen = new Set()
    const unique = []
    entries.forEach((e) => {
      if (!seen.has(e.title)) {
        seen.add(e.title)
        unique.push(e)
      }
    })
    return unique
  }

  const extractTitlesFromArticles = (articles) => {
    if (!Array.isArray(articles)) {
      return []
    }
    const titles = articles
      .map((item) => (item?.title || '').replace(/[{}]/g, '').trim())
      .filter((title) => title.length > 0)
    const seen = new Set()
    const uniqueTitles = []
    titles.forEach((title) => {
      if (!seen.has(title)) {
        seen.add(title)
        uniqueTitles.push(title)
      }
    })
    return uniqueTitles
  }

  // 将后端学者文章接口返回的 citations（SerpAPI google_scholar_author 结构）转为与模糊搜索一致的条目格式，便于创建任务时传作者等信息
  const extractEntriesFromScholarArticles = (citations) => {
    if (!Array.isArray(citations)) return []
    const parseAuthors = (authors) => {
      if (Array.isArray(authors)) return authors.map((a) => (a?.name ?? a).toString().trim()).filter(Boolean)
      if (typeof authors === 'string') return authors.split(',').map((a) => a.trim()).filter(Boolean)
      return []
    }
    const entries = citations
      .map((item) => {
        const title = (item?.title || '').replace(/[{}]/g, '').trim()
        if (!title) return null
        const citedBy = item.cited_by || item.cited_by_link
        const citationNumber = citedBy?.value ?? citedBy?.total ?? item.citation_number
        const citeLink = citedBy?.serpapi_link ?? citedBy?.serpapi_scholar_link ?? item.cite_link
        return {
          title,
          authors: parseAuthors(item.authors),
          link: item.link || undefined,
          url: item.link || undefined,
          result_id: item.citation_id ?? item.result_id,
          citation_number: citationNumber,
          cite_link: citeLink,
          summary: item.publication ?? item.summary
        }
      })
      .filter(Boolean)
    const seen = new Set()
    const unique = []
    entries.forEach((e) => {
      if (!seen.has(e.title)) {
        seen.add(e.title)
        unique.push(e)
      }
    })
    return unique
  }

  const fetchScholarArticles = async (authorId) => {
    const encodedId = encodeURIComponent(authorId)
    let lastError = null

    for (const baseUrl of [API_BASE_URL]) {
      try {
        const getResponse = await apiFetch(
          `${baseUrl}/authors/${encodedId}/articles`
        )
        if (!getResponse.ok) {
          const errorText = await getResponse.text()
          console.error('获取学者论文失败，HTTP状态码:', getResponse.status, errorText)
          lastError = new Error('fetch_failed')
          continue
        }
        const result = await getResponse.json()
        if (result.success === true && result.data) {
          const citations = result.data.citations || result.data
          return Array.isArray(citations) ? citations : []
        }
        lastError = new Error(result.message || 'fetch_failed')
      } catch (error) {
        lastError = error
      }
    }

    throw lastError || new Error('fetch_failed')
  }

  const parseScholarIdFromInput = (inputValue) => {
    const raw = (inputValue || '').trim()
    if (!raw) {
      return ''
    }

    // 兼容直接输入 ID，避免影响现有可用性
    if (!raw.includes('scholar.google')) {
      return raw
    }

    try {
      const normalized = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`
      const url = new URL(normalized)
      const isScholarHost = url.hostname.includes('scholar.google')
      if (!isScholarHost) {
        return ''
      }
      return (url.searchParams.get('user') || '').trim()
    } catch (error) {
      return ''
    }
  }

  // 通过论文标题查找 paper_id 和状态
  const findPaperIdAndStatusByTitle = async (title) => {
    try {
      const response = await apiFetch(`${API_BASE_URL}/papers`)
      const result = await response.json()
      if (result.success && result.data) {
        const paper = result.data.find(p => p.title === title || p.title?.includes(title) || title?.includes(p.title))
        if (paper) {
          return {
            paperId: paper.id,
            status: paper.analysis_status || 'CREATED'
          }
        }
      }
    } catch (error) {
      console.error('查找论文状态失败:', error)
    }
    return null
  }

  // 加载所有论文的状态
  const loadPaperStatuses = async () => {
    try {
      const response = await apiFetch(`${API_BASE_URL}/papers`)
      const result = await response.json()
      if (result.success && result.data) {
        const statusMap = {}
        result.data.forEach(paper => {
          // 使用论文标题作为key
          statusMap[paper.title] = {
            paperId: paper.id,
            status: paper.analysis_status || 'CREATED'
          }
        })
        setPaperStatusMap(statusMap)
      }
    } catch (error) {
      console.error('加载论文状态失败:', error)
    }
  }

  // 从后端加载任务
  const loadTasksFromBackend = async () => {
    try {
      const response = await apiFetch(`${API_BASE_URL}/papers`)
      const result = await response.json()
      
      if (result.success && result.data && Array.isArray(result.data)) {
        // 将后端论文数据映射为前端任务格式
        const mappedTasks = result.data.map((paper) => {
            const status = paper.analysis_status || 'CREATED'
          
          // 从后端数据中获取字段
          const citationCount = paper.citation_count || 0
          const notDownloadedCount = paper.not_downloaded_count || 0
          // 已下载数 = 总引文数 - 未下载数
          const downloadedCount = Math.max(0, citationCount - notDownloadedCount)
          // 已分析数，尝试多个可能的字段名
          const analysedCount = paper.analysed_count || paper.analyzed_count || 0
            
            // 处理 authors 字段，可能是数组或 JSON 字符串
            let authors = []
            if (paper.authors) {
              if (Array.isArray(paper.authors)) {
                authors = paper.authors
              } else if (typeof paper.authors === 'string') {
                try {
                  authors = JSON.parse(paper.authors)
                } catch (e) {
                  // 如果解析失败，尝试按逗号分割
                  authors = paper.authors.split(',').map(a => a.trim()).filter(Boolean)
                }
              }
            }
            
            return {
              id: String(paper.id), // 转换为字符串以匹配前端格式
              name: paper.title || '未命名论文',
              description: paper.doi ? `DOI: ${paper.doi}` : '无描述',
              createdAt: paper.created_at || paper.updated_at || new Date().toISOString(),
            citationCount: citationCount,
            downloadedCount: downloadedCount,
            analysedCount: analysedCount,
              paperId: paper.id, // 保存后端ID用于API调用
              analysisStatus: status,
              authors: authors // 添加作者字段
            }
          })
        setTasks(mappedTasks)
        // 更新之前的任务数据引用
        previousTasksRef.current = mappedTasks
        
        // 同时更新状态映射
        const statusMap = {}
        result.data.forEach(paper => {
          statusMap[paper.title] = {
            paperId: paper.id,
            status: paper.analysis_status || 'CREATED'
          }
        })
        setPaperStatusMap(statusMap)
      } else {
        // 如果没有数据，设置为空数组
        setTasks([])
        if (result.code === 404) {
          // 404表示没有数据，这是正常的，不需要警告
          console.log('暂无任务数据')
        } else {
          message.warning('暂无任务数据')
        }
      }
    } catch (error) {
      console.error('加载任务失败:', error)
      message.error('加载任务失败，请检查后端服务是否正常运行')
      setTasks([])
    }
  }

  // 从后端加载任务
  useEffect(() => {
    loadTasksFromBackend()
  }, [])

  // 定期刷新任务列表
  useEffect(() => {
    const interval = setInterval(() => {
      loadTasksFromBackend()
    }, 5000) // 每5秒刷新一次

    return () => clearInterval(interval)
  }, [])

  // 保存任务到后端（不再使用localStorage）
  // 此函数保留用于向后兼容，但实际数据已从后端获取

  const handleAdd = () => {
    setEditingTask(null)
    form.resetFields()
    setFuzzySearchResults([])
    setSelectedFuzzyResult(null)
    setIsModalVisible(true)
  }

  // 模糊搜索论文
  const handleFuzzySearch = async () => {
    // 先尝试从表单获取值
    let title = form.getFieldValue('name')
    
    // 如果表单值获取不到，尝试从输入框ref获取（支持Ant Design Input组件的不同版本）
    if (!title && searchInputRef.current) {
      // Ant Design 4.x: searchInputRef.current.input.value
      // Ant Design 5.x: searchInputRef.current.input?.value 或 searchInputRef.current.value
      const inputElement = searchInputRef.current.input || searchInputRef.current
      title = inputElement?.value || inputElement?.input?.value
    }
    
    // 如果还是获取不到，尝试从DOM元素获取（兜底方案）
    if (!title) {
      const inputElement = document.querySelector('input[placeholder="请输入论文名或点击搜索进行模糊搜索"]')
      if (inputElement) {
        title = inputElement.value
      }
    }
    
    // 清理空白字符
    title = title ? title.trim() : ''
    
    if (!title) {
      message.warning('请输入要搜索的论文标题')
      return
    }

    setIsFuzzySearching(true)
    setFuzzySearchResults([])
    setSelectedFuzzyResult(null)

    try {
      const response = await apiFetch(`${API_BASE_URL}/papers/fuzzy_search?title=${encodeURIComponent(title.trim())}`)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('模糊搜索失败，HTTP状态码:', response.status, errorText)
        message.error('搜索失败，请稍后重试')
        return
      }

      const result = await response.json()
      
      if (result.success && result.data && Array.isArray(result.data)) {
        if (result.data.length === 0) {
          message.info('未找到相关论文，请尝试其他关键词')
        } else {
          setFuzzySearchResults(result.data)
          message.success(`找到 ${result.data.length} 篇相关论文`)
        }
      } else {
        message.warning(result.message || '搜索返回数据格式异常')
      }
    } catch (error) {
      console.error('模糊搜索失败:', error)
      message.error('搜索失败，请检查后端服务是否正常运行')
    } finally {
      setIsFuzzySearching(false)
    }
  }

  // 选择搜索结果
  const handleSelectFuzzyResult = (result) => {
    setSelectedFuzzyResult(result)
    form.setFieldsValue({ name: result.title })
  }

  const handleBatchOpen = () => {
    setIsBatchModalVisible(true)
    setBatchFile(null)
    setBatchTitles([])
    setBatchEntries([])
    setSelectedBatchTitles([])
    setBatchParseError('')
    setBatchSearchKeyword('')
    setBatchMode('bib')
    setScholarIdInput('')
    if (batchFileInputRef.current) {
      batchFileInputRef.current.value = ''
    }
  }

  const handleBatchFileChange = (event) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    if (!file.name.toLowerCase().endsWith('.bib')) {
      message.error('请上传 .bib 格式的 BibTex 文件')
      event.target.value = ''
      setBatchTitles([])
      setBatchParseError('')
      setBatchSearchKeyword('')
      return
    }
    setBatchFile(file)
    setBatchParseError('')
    setBatchSearchKeyword('')
    setScholarIdInput('')
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const content = reader.result ? String(reader.result) : ''
        const entries = parseBibtexEntries(content)
        const titles = entries.map((e) => e.title)
        setBatchEntries(entries)
        setBatchTitles(titles)
        setSelectedBatchTitles(titles)
        setBatchSearchKeyword('')
        if (titles.length === 0) {
          setBatchParseError('未解析到标题，请检查 BibTex 文件内容')
        }
      } catch (error) {
        console.error('解析 BibTex 失败:', error)
        setBatchParseError('解析失败，请确认文件格式正确')
        setBatchTitles([])
        setBatchEntries([])
        setSelectedBatchTitles([])
      }
    }
    reader.onerror = () => {
      setBatchParseError('读取文件失败，请重试')
      setBatchTitles([])
      setBatchEntries([])
      setSelectedBatchTitles([])
    }
    reader.readAsText(file)
  }

  const handleBatchUpload = async () => {
    if (batchMode === 'scholar' && batchTitles.length === 0) {
      const authorId = parseScholarIdFromInput(scholarIdInput)
      if (!authorId) {
        message.error('请输入有效的 Google Scholar 学者主页 URL')
        return
      }
      setIsScholarLoading(true)
      try {
        const citations = await fetchScholarArticles(authorId)
        const entries = extractEntriesFromScholarArticles(citations)
        const titles = extractTitlesFromArticles(citations)
        setBatchEntries(entries)
        setBatchTitles(titles)
        setSelectedBatchTitles(titles)
        if (titles.length === 0) {
          setBatchParseError('未获取到论文标题，请检查学者主页 URL')
          setIsScholarLoading(false)
          return
        }
      } catch (error) {
        message.error('获取学者论文失败，请检查后端服务是否正常运行')
        setIsScholarLoading(false)
        return
      } finally {
        setIsScholarLoading(false)
      }
    }
    if (batchTitles.length === 0) {
      message.error('请先选择 BibTex 文件或检索学者论文')
      return
    }
    if (selectedBatchTitles.length === 0) {
      message.error('请先选择要创建的论文标题')
      return
    }

    setIsBatchUploading(true)
    try {
      let createdCount = 0
      let failedCount = 0
      for (const title of selectedBatchTitles) {
        try {
          // 仿照模糊搜索创建任务：若有解析出的条目则传 authors、link、result_id、citation_number、cite_link、summary 等
          const entry = batchEntries.find((e) => e.title === title)
          const requestBody = entry
            ? {
                title: entry.title,
                authors: entry.authors || [],
                ...(entry.link || entry.url ? { link: entry.link || entry.url } : {}),
                ...(entry.doi ? { doi: entry.doi } : {}),
                ...(entry.result_id != null ? { result_id: entry.result_id } : {}),
                ...(entry.citation_number != null ? { citation_number: entry.citation_number } : {}),
                ...(entry.cite_link ? { cite_link: entry.cite_link } : {}),
                ...(entry.summary ? { summary: entry.summary } : {})
              }
            : { title: title.trim() }
          const response = await apiFetch(`${API_BASE_URL}/papers`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
          })

          if (!response.ok) {
            failedCount += 1
            continue
          }

          const result = await response.json()
          if (result.success === true && result.data) {
            createdCount += 1
          } else {
            failedCount += 1
          }
        } catch (error) {
          console.error('创建论文失败:', error)
          failedCount += 1
        }
      }

      message.success(`批量创建完成：成功 ${createdCount}，失败 ${failedCount}`)
      setIsBatchModalVisible(false)
      setBatchFile(null)
      setBatchTitles([])
      setBatchEntries([])
      setSelectedBatchTitles([])
      setScholarIdInput('')
      await loadTasksFromBackend()
    } catch (error) {
      console.error('批量上传失败:', error)
      message.error('批量上传失败，请检查后端服务是否正常运行')
    } finally {
      setIsBatchUploading(false)
    }
  }

  const handleDeletePaper = async (paperId) => {
    try {
      if (!paperId) {
        message.error('无法找到对应的论文ID')
        return
      }
      
      const response = await apiFetch(`${API_BASE_URL}/papers/${paperId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        }
      })
      
      // 检查HTTP状态码
      if (!response.ok) {
        const errorText = await response.text()
        console.error('删除失败，HTTP状态码:', response.status, errorText)
        message.error(`删除失败: ${response.status === 404 ? '论文不存在' : '服务器错误'}`)
        return
      }
      
      const result = await response.json()
      
      // 后端返回格式: {"success": true/false}
      if (result.success === true) {
        return true
      } else {
        message.error('删除失败: 后端返回失败')
        return false
      }
    } catch (error) {
      console.error('删除任务失败:', error)
      message.error('删除任务失败，请检查后端服务是否正常运行')
      return false
    }
  }

  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要删除的任务')
      return
    }
    let successCount = 0
    let failedCount = 0
    for (const id of selectedRowKeys) {
      const task = tasks.find(t => t.id === id)
      const paperId = task?.paperId || id
      const ok = await handleDeletePaper(paperId)
      if (ok) {
        successCount += 1
      } else {
        failedCount += 1
      }
    }
    message.success(`批量删除完成：成功 ${successCount}，失败 ${failedCount}`)
    setSelectedRowKeys([])
    await loadTasksFromBackend()
  }

  // 单个任务开始分析
  const handleStartAnalysis = async (task) => {
    const paperId = task?.paperId || task?.id
    if (!paperId) {
      message.error('无法找到论文ID')
      return
    }
    
    const status = getTaskStatus(task)
    if (status === 'ANALYZING' || status === 'COMPLETED') {
      message.warning('该任务已经在分析中或已完成')
      return
    }
    
    try {
      const endpoint = status === 'DOWNLOADED'
        ? `${API_BASE_URL}/analysis/${paperId}`
        : `${API_BASE_URL}/analysis_download/${paperId}`
      
      const response = await apiFetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      })
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('开始分析失败，HTTP状态码:', response.status, errorText)
        message.error('开始分析失败，请稍后重试')
        return
      }
      
      const result = await response.json()
      if (result.success === true) {
        message.success('分析任务已启动，正在后台处理中...')
        // 重新加载任务列表以更新状态
        await loadTasksFromBackend()
      } else {
        message.error(result.message || '开始分析失败')
      }
    } catch (error) {
      console.error('开始分析失败:', error)
      message.error('开始分析失败，请检查后端服务是否正常运行')
    }
  }

  const handleBatchStartAnalysis = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要开始分析的任务')
      return
    }
    setIsBatchAnalyzing(true)
    let successCount = 0
    let failedCount = 0
    let skippedCount = 0
    for (const id of selectedRowKeys) {
      const task = tasks.find(t => t.id === id)
      const paperId = task?.paperId || id
      if (!paperId) {
        failedCount += 1
        continue
      }
      const status = getTaskStatus(task)
      if (status === 'ANALYZING' || status === 'COMPLETED') {
        skippedCount += 1
        continue
      }
      const endpoint = status === 'DOWNLOADED'
        ? `${API_BASE_URL}/analysis/${paperId}`
        : `${API_BASE_URL}/analysis_download/${paperId}`
      try {
        const response = await apiFetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        })
        if (!response.ok) {
          failedCount += 1
          continue
        }
        const result = await response.json()
        if (result.success === true) {
          successCount += 1
        } else {
          failedCount += 1
        }
      } catch (error) {
        console.error('开始分析失败:', error)
        failedCount += 1
      }
    }
    message.success(`批量开始分析完成：成功 ${successCount}，失败 ${failedCount}，跳过 ${skippedCount}`)
    await loadTasksFromBackend()
    setIsBatchAnalyzing(false)
  }
  const handleModalOk = async (action = 'create') => {
    try {
      const values = await form.validateFields()
      if (editingTask) {
        // 编辑 - 调用后端PUT接口
        if (!values.name || !values.name.trim()) {
          message.error('请输入论文名')
          return
        }
        
        const paperId = editingTask.paperId || editingTask.id
        if (!paperId) {
          message.error('无法找到对应的论文ID')
          return
        }
        
        const response = await apiFetch(`${API_BASE_URL}/papers/${paperId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            title: values.name.trim()
          })
        })
        
        // 检查HTTP状态码
        if (!response.ok) {
          const errorText = await response.text()
          console.error('更新失败，HTTP状态码:', response.status, errorText)
          message.error(`更新失败: ${response.status === 404 ? '论文不存在' : response.status === 400 ? '请求参数错误' : '服务器错误'}`)
          return
        }
        
        const result = await response.json()
        
        // 后端返回格式: {"success": true/false}
        if (result.success === true) {
          message.success('任务更新成功')
          // 关闭模态框
          setIsModalVisible(false)
          form.resetFields()
          setEditingTask(null)
          // 重新加载任务列表
          await loadTasksFromBackend()
        } else {
          message.error(result.message || '更新失败')
        }
      } else {
        // 新增 - 调用后端POST接口
        if (!values.name || !values.name.trim()) {
          message.error('请输入论文名')
          return
        }
        
        // 如果用户选择了搜索结果，使用搜索结果的完整信息
        let requestBody = {
          title: values.name.trim()
        }
        
        if (selectedFuzzyResult) {
          // 使用搜索结果中的完整信息
          requestBody = {
            title: selectedFuzzyResult.title || values.name.trim(),
            result_id: selectedFuzzyResult.result_id,
            link: selectedFuzzyResult.link,
            authors: selectedFuzzyResult.authors || [],
            citation_number: selectedFuzzyResult.citation_number,
            cite_link: selectedFuzzyResult.cite_link,
            summary: selectedFuzzyResult.summary
          }
        }
        
        const response = await apiFetch(`${API_BASE_URL}/papers`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestBody)
        })
        
        // 检查HTTP状态码
        if (!response.ok) {
          const errorText = await response.text()
          console.error('创建失败，HTTP状态码:', response.status, errorText)
          message.error(`创建失败: ${response.status === 400 ? '请求参数错误' : response.status === 500 ? '服务器错误' : '未知错误'}`)
          return
        }
        
        const result = await response.json()
        
        // 后端返回格式: { success: true, code: 200, message: "success", data: paper_id }
        if (result.success === true && result.data) {
          const createdPaperId = result.data
          if (action === 'createAndAnalyze') {
            const analysisResponse = await apiFetch(`${API_BASE_URL}/analysis_download/${createdPaperId}`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json'
              }
            })
            if (!analysisResponse.ok) {
              const analysisErrorText = await analysisResponse.text()
              console.error('创建后启动分析失败，HTTP状态码:', analysisResponse.status, analysisErrorText)
              message.warning('任务已创建，但自动开始分析失败，请手动开始分析')
            } else {
              const analysisResult = await analysisResponse.json()
              if (analysisResult.success === true) {
                message.success('任务创建成功，分析已启动')
              } else {
                message.warning('任务已创建，但自动开始分析失败，请手动开始分析')
              }
            }
          } else {
            message.success('任务创建成功')
          }
          // 关闭模态框
          setIsModalVisible(false)
          form.resetFields()
          setFuzzySearchResults([])
          setSelectedFuzzyResult(null)
          // 重新加载任务列表
          await loadTasksFromBackend()
        } else {
          message.error(result.message || '创建失败')
        }
      }
    } catch (error) {
      console.error('操作失败:', error)
      message.error('操作失败，请检查后端服务')
    }
  }

  const handleModalCancel = () => {
    setIsModalVisible(false)
    form.resetFields()
    setEditingTask(null)
    setFuzzySearchResults([])
    setSelectedFuzzyResult(null)
  }

  const handleBatchCancel = () => {
    setIsBatchModalVisible(false)
    setBatchFile(null)
    setBatchTitles([])
    setSelectedBatchTitles([])
    setBatchParseError('')
    setBatchSearchKeyword('')
    setScholarIdInput('')
    if (batchFileInputRef.current) {
      batchFileInputRef.current.value = ''
    }
  }

  const handleScholarSearch = async () => {
    const authorId = parseScholarIdFromInput(scholarIdInput)
    if (!authorId) {
      message.error('请输入有效的 Google Scholar 学者主页 URL')
      return
    }
    setIsScholarLoading(true)
    try {
      const citations = await fetchScholarArticles(authorId)
      const entries = extractEntriesFromScholarArticles(citations)
      const titles = extractTitlesFromArticles(citations)
      setBatchEntries(entries)
      setBatchTitles(titles)
      setSelectedBatchTitles(titles)
      setBatchSearchKeyword('')
      if (titles.length === 0) {
        setBatchParseError('未获取到论文标题，请检查学者主页 URL')
      } else {
        setBatchParseError('')
        message.success(`已获取到 ${titles.length} 篇论文`)
      }
      setBatchFile(null)
      if (batchFileInputRef.current) {
        batchFileInputRef.current.value = ''
      }
    } catch (error) {
      console.error('获取学者论文失败:', error)
      message.error('获取学者论文失败，请检查后端服务是否正常运行')
    } finally {
      setIsScholarLoading(false)
    }
  }

  const handleViewAnalysis = (taskId) => {
    // 查找对应的paperId
    const task = tasks.find(t => t.id === taskId)
    const paperId = task?.paperId || taskId
    navigate(`/analysis/${paperId}`)
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

  // 过滤任务
  const getFilteredAndSortedTasks = () => {
    let filtered = tasks

    // 搜索过滤
    if (searchKeyword.trim()) {
      const keyword = searchKeyword.toLowerCase()
      filtered = filtered.filter(task => {
        const nameMatched = task.name && task.name.toLowerCase().includes(keyword)
        const authorsMatched = Array.isArray(task.authors)
          ? task.authors.some((author) =>
              String(author || '').toLowerCase().includes(keyword)
            )
          : false
        return nameMatched || authorsMatched
      })
    }
    return filtered
  }

  // 获取状态显示配置（覆盖后端已使用与历史可能返回的状态值）
  const getStatusConfig = (status) => {
    const normalizedStatus = String(status || '')
      .trim()
      .toUpperCase()
      .replace(/[\s-]+/g, '_')

    const statusConfig = {
      CREATED: { color: 'default', text: '已创建' },
      DOWNLOADING: { color: 'processing', text: '下载中' },
      DOWNLOADED: { color: 'blue', text: '已下载' },
      ANALYZING: { color: 'processing', text: '分析中' },
      COMPLETED: { color: 'success', text: '已完成' },
      DOWNLOAD_FAILED: { color: 'error', text: '下载失败' },
      ANALYSIS_FAILED: { color: 'error', text: '分析失败' },
      FAILED: { color: 'error', text: '失败' },
      ERROR: { color: 'error', text: '错误' },
      PENDING: { color: 'warning', text: '等待中' },
      QUEUED: { color: 'warning', text: '排队中' }
    }

    if (statusConfig[normalizedStatus]) {
      return statusConfig[normalizedStatus]
    }

    return { color: 'default', text: normalizedStatus || '未知状态' }
  }

  // 获取任务状态
  const getTaskStatus = (task) => {
    // 优先使用task中的analysisStatus
    if (task.analysisStatus) {
      return task.analysisStatus
    }
    
    // 回退到从状态映射中查找
    const taskName = task.name || ''
    let statusInfo = paperStatusMap[taskName]
    
    // 如果精确匹配失败，尝试模糊匹配
    if (!statusInfo) {
      const matchedKey = Object.keys(paperStatusMap).find(key => 
        key.includes(taskName) || taskName.includes(key)
      )
      if (matchedKey) {
        statusInfo = paperStatusMap[matchedKey]
      }
    }
    
    return statusInfo?.status || 'CREATED'
  }

  const filteredBatchTitles = batchTitles.filter((title) => {
    if (!batchSearchKeyword.trim()) {
      return true
    }
    return title.toLowerCase().includes(batchSearchKeyword.trim().toLowerCase())
  })

  const createTaskMenuItems = [
    {
      key: 'single',
      label: '单个任务创建',
      icon: <PlusOutlined />,
      onClick: handleAdd
    },
    {
      key: 'batch',
      label: '批量创建任务',
      icon: <UploadOutlined />,
      onClick: handleBatchOpen
    }
  ]

  const columns = [
    {
      title: '论文名',
      dataIndex: 'name',
      key: 'name',
      width: '25%',
      sorter: (a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'zh-CN'),
      render: (name) => name || '-'
    },
    {
      title: '作者',
      key: 'authors',
      width: '20%',
      sorter: (a, b) => {
        const authorsA = Array.isArray(a.authors) ? a.authors.join(', ') : ''
        const authorsB = Array.isArray(b.authors) ? b.authors.join(', ') : ''
        return authorsA.localeCompare(authorsB, 'zh-CN')
      },
      render: (_, record) => {
        const authors = record.authors || []
        if (Array.isArray(authors) && authors.length > 0) {
          const keyword = searchKeyword.trim()
          if (!keyword) {
            return <span>{authors.join(', ')}</span>
          }
          return (
            <span>
              {authors.map((author, index) => (
                <React.Fragment key={`${author}-${index}`}>
                  {index > 0 ? ', ' : ''}
                  {highlightMatchedText(author, keyword)}
                </React.Fragment>
              ))}
            </span>
          )
        }
        return <span style={{ color: '#999' }}>-</span>
      }
    },
    {
      title: '总引文数/已下载/已分析',
      key: 'citationStats',
      width: '13%',
      sorter: (a, b) => {
        const citationDiff = (a.citationCount || 0) - (b.citationCount || 0)
        if (citationDiff !== 0) return citationDiff
        const downloadedDiff = (a.downloadedCount || 0) - (b.downloadedCount || 0)
        if (downloadedDiff !== 0) return downloadedDiff
        return (a.analysedCount || 0) - (b.analysedCount || 0)
      },
      render: (_, record) => {
        const citationCount = record.citationCount || 0
        const downloadedCount = record.downloadedCount || 0
        const analysedCount = record.analysedCount || 0
        return `${citationCount}/${downloadedCount}/${analysedCount}`
      }
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: '15%',
      sorter: (a, b) => {
        const normalize = (time) => (
          typeof time === 'string' && time.includes(' ') ? `${time.replace(' ', 'T')}Z` : time
        )
        const timeA = new Date(normalize(a.createdAt) || 0).getTime()
        const timeB = new Date(normalize(b.createdAt) || 0).getTime()
        return timeA - timeB
      },
      render: (time) => {
        if (!time) {
          return '-'
        }
        const normalized = typeof time === 'string' && time.includes(' ') ? time.replace(' ', 'T') + 'Z' : time
        return new Date(normalized).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
      }
    },
    {
      title: '任务状态',
      key: 'status',
      width: '12%',
      sorter: (a, b) => {
        const getStatusOrder = (status) => {
          const key = String(status || '').trim().toUpperCase().replace(/[\s-]+/g, '_')
          if (key === 'CREATED') return 0
          if (key === 'PENDING' || key === 'QUEUED') return 1
          if (key === 'DOWNLOADING' || key === 'DOWNLOADED') return 2
          if (key === 'ANALYZING') return 3
          if (key === 'COMPLETED') return 4
          if (key === 'DOWNLOAD_FAILED' || key === 'ANALYSIS_FAILED' || key === 'FAILED' || key === 'ERROR') return 5
          return 6
        }
        return getStatusOrder(getTaskStatus(a)) - getStatusOrder(getTaskStatus(b))
      },
      render: (_, record) => {
        const status = getTaskStatus(record)
        const config = getStatusConfig(status)
        return <Tag color={config.color}>{config.text}</Tag>
      }
    },
    {
      title: '操作',
      key: 'action',
      width: '15%',
      sorter: (a, b) => {
        const getActionValue = (task) => {
          const status = getTaskStatus(task)
          if (status === 'CREATED') return 0
          if (status === 'DOWNLOADING' || status === 'DOWNLOADED') return 1
          if (status === 'ANALYZING') return 2
          return 3
        }
        return getActionValue(a) - getActionValue(b)
      },
      render: (_, record) => {
        const status = getTaskStatus(record)
        const cannotStart = status === 'ANALYZING' || status === 'COMPLETED'

        return (
          <Space>
            <Tooltip title="开始分析">
              <Button
                type="text"
                size="small"
                icon={<PlayCircleOutlined />}
                disabled={cannotStart}
                onClick={() => handleStartAnalysis(record)}
              />
            </Tooltip>
            <Tooltip title="查看">
              <Button
                type="text"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => handleViewAnalysis(record.id)}
              />
            </Tooltip>
            <Popconfirm
              title="确定删除该任务吗？"
              onConfirm={async () => {
                const paperId = record?.paperId || record?.id
                const ok = await handleDeletePaper(paperId)
                if (ok) {
                  message.success('任务删除成功')
                  await loadTasksFromBackend()
                }
              }}
              okText="确定"
              cancelText="取消"
            >
              <Tooltip title="删除">
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        )
      },
    },
  ]

  return (
    <div className="task-management-page">
      <Card>
        <div className="page-header">
          <div className="header-content">
            <Title level={2}>任务管理</Title>
            <Space>
              <Dropdown
                menu={{ items: createTaskMenuItems }}
                trigger={['click']}
                placement="bottomRight"
              >
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  size="large"
                >
                  新建任务 <DownOutlined />
                </Button>
              </Dropdown>
              <Popconfirm
                title={`确定要开始分析选中的 ${selectedRowKeys.length} 个任务吗？`}
                onConfirm={handleBatchStartAnalysis}
                okText="确定"
                cancelText="取消"
                disabled={selectedRowKeys.length === 0}
              >
                <Button
                  icon={<PlayCircleOutlined />}
                  size="large"
                  disabled={selectedRowKeys.length === 0}
                  loading={isBatchAnalyzing}
                >
                  批量分析
                </Button>
              </Popconfirm>
              <Popconfirm
                title={`确定要删除选中的 ${selectedRowKeys.length} 个任务吗？`}
                onConfirm={handleBatchDelete}
                okText="确定"
                cancelText="取消"
                disabled={selectedRowKeys.length === 0}
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  size="large"
                  disabled={selectedRowKeys.length === 0}
                >
                  批量删除
                </Button>
              </Popconfirm>
            </Space>
          </div>
        </div>

        {/* 搜索和排序工具栏 */}
        <div style={{ marginBottom: 16, display: 'flex', gap: 16, alignItems: 'center' }}>
          <Input
            placeholder="搜索论文名或作者"
            prefix={<SearchOutlined />}
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            allowClear
            style={{ width: 300 }}
          />
          <span style={{ color: '#999', fontSize: '14px' }}>
            共 {getFilteredAndSortedTasks().length} 个任务
          </span>
        </div>

        <Table
          columns={columns}
          dataSource={getFilteredAndSortedTasks()}
          showSorterTooltip={false}
          rowKey="id"
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys)
          }}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title={editingTask ? '编辑任务' : '新建任务'}
        open={isModalVisible}
        onOk={() => handleModalOk('create')}
        onCancel={handleModalCancel}
        okText={editingTask ? '确定' : '创建'}
        cancelText="取消"
        width={800}
        footer={
          editingTask
            ? undefined
            : [
                <Button key="cancel" onClick={handleModalCancel}>
                  取消
                </Button>,
                <Button key="create" type="primary" onClick={() => handleModalOk('create')}>
                  创建
                </Button>,
                <Button key="createAndAnalyze" type="primary" onClick={() => handleModalOk('createAndAnalyze')}>
                  创建并分析
                </Button>
              ]
        }
      >
        <Form
          form={form}
          layout="vertical"
        >
          <Form.Item
            name="name"
            label="论文名"
            rules={[{ required: true, message: '请输入论文名' }]}
          >
            <Space.Compact style={{ width: '100%' }}>
              <Input
                ref={searchInputRef}
                placeholder="请输入论文名或点击搜索进行模糊搜索"
                disabled={!!editingTask}
                onPressEnter={!editingTask ? handleFuzzySearch : undefined}
                onChange={(e) => {
                  // 确保表单值实时更新
                  form.setFieldsValue({ name: e.target.value })
                }}
              />
              {!editingTask && (
                <Button
                  type="primary"
                  icon={<SearchOutlined />}
                  loading={isFuzzySearching}
                  onClick={handleFuzzySearch}
                >
                  搜索
                </Button>
              )}
            </Space.Compact>
          </Form.Item>
          
          {/* 搜索结果列表 */}
          {!editingTask && fuzzySearchResults.length > 0 && (
            <Form.Item label="搜索结果（请选择一篇论文）">
              <div style={{ maxHeight: '400px', overflowY: 'auto', border: '1px solid #d9d9d9', borderRadius: '4px', padding: '8px' }}>
                {fuzzySearchResults.map((result, index) => (
                  <div
                    key={index}
                    onClick={() => handleSelectFuzzyResult(result)}
                    style={{
                      padding: '12px',
                      marginBottom: '8px',
                      border: selectedFuzzyResult === result ? '2px solid #22c55e' : '1px solid #e8e8e8',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      backgroundColor: selectedFuzzyResult === result ? '#f0fdf4' : '#fff',
                      transition: 'all 0.3s'
                    }}
                    onMouseEnter={(e) => {
                      if (selectedFuzzyResult !== result) {
                        e.currentTarget.style.backgroundColor = '#f5f5f5'
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (selectedFuzzyResult !== result) {
                        e.currentTarget.style.backgroundColor = '#fff'
                      }
                    }}
                  >
                    <div style={{ fontWeight: 'bold', marginBottom: '4px', color: '#16a34a' }}>
                      {result.title}
                    </div>
                    {result.authors && result.authors.length > 0 && (
                      <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>
                        作者: {result.authors.join(', ')}
                      </div>
                    )}
                    {result.citation_number !== undefined && (
                      <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>
                        引用数: {result.citation_number}
                      </div>
                    )}
                    {result.summary && (
                      <div style={{ fontSize: '12px', color: '#999', marginTop: '4px', maxHeight: '40px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {result.summary}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title="批量创建任务"
        open={isBatchModalVisible}
        onOk={handleBatchUpload}
        onCancel={handleBatchCancel}
        okText="上传并创建"
        cancelText="取消"
        confirmLoading={isBatchUploading}
        width={600}
      >
        <div className="batch-upload">
          <Radio.Group
            value={batchMode}
            onChange={(e) => {
              const nextMode = e.target.value
              setBatchMode(nextMode)
              setBatchTitles([])
              setSelectedBatchTitles([])
              setBatchParseError('')
              setBatchSearchKeyword('')
              if (nextMode === 'bib') {
                setScholarIdInput('')
              } else {
                setBatchFile(null)
                if (batchFileInputRef.current) {
                  batchFileInputRef.current.value = ''
                }
              }
            }}
          >
            <Radio.Button value="bib">上传 BibTex 文件</Radio.Button>
            <Radio.Button value="scholar">输入学者主页 URL</Radio.Button>
          </Radio.Group>

          {batchMode === 'bib' ? (
            <>
              <input
                ref={batchFileInputRef}
                type="file"
                accept=".bib"
                onChange={handleBatchFileChange}
                style={{ display: 'none' }}
              />
              <Space>
                <Button onClick={() => batchFileInputRef.current?.click()}>
                  选择 BibTex 文件
                </Button>
                <span className="batch-upload-filename">
                  {batchFile ? batchFile.name : '未选择文件'}
                </span>
              </Space>
              <div className="batch-upload-tip">
                支持 .bib 文件，读取条目中的 title 字段并批量创建任务。
              </div>
            </>
          ) : (
            <>
              <Space>
                <Input
                  placeholder="请输入 Google Scholar 学者主页 URL（如 https://scholar.google.com/citations?user=PPqcVRwAAAAJ&hl=zh-CN）"
                  value={scholarIdInput}
                  onChange={(e) => setScholarIdInput(e.target.value)}
                  style={{ width: 460 }}
                />
                <Button
                  type="primary"
                  onClick={handleScholarSearch}
                  loading={isScholarLoading}
                >
                  检索论文
                </Button>
              </Space>
              <div className="batch-upload-tip">
                从学者主页检索论文列表，并支持批量创建任务。
              </div>
            </>
          )}
          <div className="batch-upload-preview">
            <div className="batch-upload-preview-header">
              预览标题（{filteredBatchTitles.length}/{batchTitles.length}）
            </div>
            <Input
              placeholder="搜索预览标题"
              value={batchSearchKeyword}
              onChange={(e) => setBatchSearchKeyword(e.target.value)}
              allowClear
            />
            <div className="batch-upload-actions">
              <Button
                size="small"
                onClick={() => {
                  const merged = new Set([...selectedBatchTitles, ...filteredBatchTitles])
                  setSelectedBatchTitles(Array.from(merged))
                }}
                disabled={filteredBatchTitles.length === 0}
              >
                全选
              </Button>
              <Button
                size="small"
                onClick={() => {
                  const filteredSet = new Set(filteredBatchTitles)
                  const remaining = selectedBatchTitles.filter((title) => !filteredSet.has(title))
                  setSelectedBatchTitles(remaining)
                }}
                disabled={filteredBatchTitles.length === 0}
              >
                清空
              </Button>
              <span className="batch-upload-selected">
                已选 {selectedBatchTitles.length}
              </span>
            </div>
            {batchParseError ? (
              <div className="batch-upload-error">{batchParseError}</div>
            ) : (
              <div className="batch-upload-preview-list">
                {filteredBatchTitles.length === 0 ? (
                  <div className="batch-upload-empty">暂无可预览标题</div>
                ) : (
                  <Checkbox.Group
                    value={selectedBatchTitles}
                    onChange={(values) => {
                      const filteredSet = new Set(filteredBatchTitles)
                      const remaining = selectedBatchTitles.filter((title) => !filteredSet.has(title))
                      setSelectedBatchTitles([...remaining, ...values])
                    }}
                  >
                    <div className="batch-upload-checkbox-list">
                      {filteredBatchTitles.map((title, index) => (
                        <label className="batch-upload-preview-item" key={`${title}-${index}`}>
                          <Checkbox value={title}>{title}</Checkbox>
                        </label>
                      ))}
                    </div>
                  </Checkbox.Group>
                )}
              </div>
            )}
          </div>
        </div>
      </Modal>
    </div>
  )
}

export default TaskManagementPage


