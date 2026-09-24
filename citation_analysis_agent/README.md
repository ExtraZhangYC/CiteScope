# Citation Analysis Agent

基于 LangChain 的多智能体引用分析系统，使用 Supervisor Agent 模式协调引用分析和情感分析。

## 项目结构

```
agent/              # 核心 agent 模块
  ├── agents.py     # Agent 定义（citation/sentiment/supervisor）
  ├── models.py     # 大模型接口
  ├── tools.py      # 工具函数（定位引用、提取特征等）
  ├── prompt.py     # Prompt 模板
  ├── workflows.py  # 工作流执行
  └── utils.py      # 工具函数（LLM配置、JSON解析）
model/              # SQLite 数据访问层
  ├── base.py       # 单例连接 + WAL + 写锁重试
  ├── model.py      # papers 表 CRUD
  ├── citation_model.py  # citations 表 CRUD
  ├── user_model.py      # users 表 CRUD
  └── report_model.py    # reports 表 CRUD
routes/             # Flask 路由（API 层）
service/            # 业务逻辑层
download/           # 论文 PDF 下载工具
utils/              # 通用工具（响应包装、鉴权）
schema.py           # 数据模型定义
text_utils.py       # 文本处理工具
storage/            # 运行时数据（papers、reports 等）
client/             # 前端
app.py              # Flask 应用入口
start_api.py        # 启动后端服务
start_agents.py     # CLI 入口：多智能体分析
start_multiprocess_service.py  # CLI 入口：多线程分析
```

## 论文文件夹结构

每个论文文件夹（如 `papers/MyPaper/`）需要包含以下文件：

### 必需文件

- **原论文文件** - 用于章节映射（通过 `--primary` 参数指定，未实现）
- **`info.json`** - 论文元数据，格式如下：
  ```json
  {
    "ScholarID": "论文ID（可选）",
    "Authors": ["作者1", "作者2"],
    "ApproachName": ["方法名称1", "方法名称2"],
    "Title": "论文标题",
    "Venue": "会议/期刊名称",
    "Year": "发表年份"
  }
  ```
- **`Citation_X.txt`** 或 **`Citation_X.pdf`** - 引用文本文件（X 为引用编号，如 1, 2, 3...）
  - 优先使用 `.txt` 文件
  - 如果只有 `.pdf`，系统会自动转换为 `.txt`

以上文件可通过原始项目爬虫获取。

## 快速开始

```bash
# 分析指定论文的所有引用
python start_agents.py papers/MyPaper \ 
    --api-key your-api-key \ 
    --base-url https://api.openai.com/v1 \ 
    --model gpt-4o-mini

# 分析特定引用ID
python start_agents.py papers/MyPaper --citations 1 2 3

# 指定原论文路径（用于章节映射，暂未实现）
python start_agents.py papers/MyPaper --primary papers/MyPaper/original.pdf
```

## 输出

分析结果保存在 `papers/MyPaper/supervisor_analysis_report.json`，包含整合后的引用分析和情感分析记录。

