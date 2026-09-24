# 🔭 CiteScope · 引用视界

> An AI-powered academic citation analysis platform that leverages LLM-driven multi-agent collaboration to assess citation impact, visualize reference networks, and evaluate scholarly influence.

基于多智能体与 LLM 的学术论文引用分析与影响力评估平台。它通过多智能体协作，自动完成论文检索、引用上下文分析、情感判定和影响力评估，帮助研究者从引用、作者、内容等多维度洞察论文价值。

---

## ✨ 核心特性

- 🤖 **多智能体协作**：基于 LangChain / LangGraph 构建 Supervisor 模式的多智能体系统，自动协调引用分析、情感分析与报告生成
- 🔍 **智能学术检索**：集成 SerpApi / Google Scholar 等学术数据源，支持论文检索、引文下载与作者画像
- 📚 **引用上下文分析**：解析每条引用在原论文中的位置与意图，识别关键参考文献与重要被引模式
- 👤 **学者影响力评估**：综合引用次数、H 指数、合作网络等多维信息，对学者进行画像
- 📊 **AI 报告生成**：由 LLM 自动生成结构化的引用分析报告与情感分析报告
- 🖥️ **现代化 Web 界面**：基于 React + Ant Design 的 SPA，支持任务管理、报告查看、可视化交互

---

## 🏗️ 项目结构

本仓库采用前后端单仓（Monorepo）结构：

```
CiteScope/
├── citation_analysis_agent/        # 后端：Python + Flask + LangChain 多智能体
│   ├── agent/                      # 智能体定义（Citation / Sentiment / Supervisor）
│   ├── routes/                     # Flask 路由（API 层）
│   ├── service/                    # 业务逻辑层
│   ├── model/                      # SQLite 数据访问层
│   ├── download/                   # 论文 PDF / 引文下载工具
│   ├── utils/                      # 通用工具
│   ├── schema.py                   # 数据模型定义
│   ├── app.py                      # Flask 应用入口
│   ├── start_api.py                # 启动后端服务
│   ├── start_agents.py             # CLI 入口：单论文分析
│   ├── start_multiprocess_service.py  # CLI 入口：多线程批处理
│   ├── requirements.txt
│   └── .env.example                # 环境变量示例
│
├── citation_analysis_front_end/    # 前端：React + Vite + Ant Design
│   ├── src/
│   │   ├── pages/                  # 页面（Welcome / Login / TaskManagement / CitationAnalysis）
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
└── README.md                       # 本文件
```

---

## 🛠️ 技术栈

### 后端
| 类别 | 技术 |
|------|------|
| Web 框架 | Flask 3 + Flask-CORS |
| 大模型编排 | LangChain 1.0 / LangGraph 1.0 |
| LLM 接入 | OpenAI 兼容协议（支持 OpenRouter / 自部署） |
| 数据持久化 | SQLite + SQLAlchemy |
| PDF / 文本处理 | PyMuPDF、BeautifulSoup |
| 学术数据源 | SerpApi（Google Scholar）、Selenium |

### 前端
| 类别 | 技术 |
|------|------|
| 框架 | React 18 + React Router v6 |
| UI 库 | Ant Design 5 |
| 构建工具 | Vite 5 |
| 状态/请求 | React Hooks（项目内自行管理） |

---

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone <your-repo-url>.git
cd CiteScope
```

### 2. 启动后端

```bash
cd citation_analysis_agent

# 准备 Python 环境（推荐 Python 3.11+）
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量：复制 .env.example 为 .env，并填入你的密钥
cp .env.example .env   # Windows: copy .env.example .env

# 启动 Flask API 服务
python app.py
# 或：python start_api.py
```

后端将运行在 `http://localhost:5000`。

### 3. 启动前端

```bash
cd ../citation_analysis_front_end

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端将运行在 `http://localhost:3000`，并通过 Vite 代理将 `/api/*` 转发到后端 `http://localhost:5000/api/*`。

### 4. CLI 模式（可选）

如果你不想启动 Web 服务，也可以直接用 CLI 对单篇论文做分析：

```bash
cd citation_analysis_agent

python start_agents.py papers/MyPaper \
    --api-key your-api-key \
    --base-url https://openrouter.ai/api/v1 \
    --model openai/gpt-4o-mini

# 分析指定引用
python start_agents.py papers/MyPaper --citations 1 2 3
```

---

## ⚙️ 环境变量

在 `citation_analysis_agent/.env` 中配置：

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | LLM 提供方密钥（OpenAI / OpenRouter 兼容协议） |
| `OPENAI_BASE_URL` | ✅ | LLM API 地址（OpenRouter：`https://openrouter.ai/api/v1`） |
| `OPENAI_MODEL` | ✅ | 模型名（如 `openai/gpt-4o-mini`） |
| `SERP_API_KEY` | ⛔ 推荐 | SerpApi Key，用于论文检索 / 引文下载 |
| `HOST` | ❌ | Flask 监听地址，默认 `0.0.0.0` |
| `PORT` | ❌ | Flask 端口，默认 `5000` |
| `DEBUG` | ❌ | 调试模式，默认 `False` |
| `HTTP_PROXY` / `HTTPS_PROXY` | ❌ | 如果本地有代理可解开注释 |
| `DATABASE_URL` | ❌ | 自定义数据库连接，默认使用项目根目录 sqlite 文件 |

> ⚠️ **永远不要把 `.env` 提交到仓库！** 本仓库的 `.gitignore` 已默认忽略它。

---

## 📄 论文文件夹结构

CLI 模式要求每篇论文以一个文件夹形式存在（如 `papers/MyPaper/`），并至少包含：

- `info.json` — 论文元数据
  ```json
  {
    "ScholarID": "论文ID（可选）",
    "Authors": ["作者1", "作者2"],
    "ApproachName": ["方法名称1"],
    "Title": "论文标题",
    "Venue": "会议/期刊名称",
    "Year": "发表年份"
  }
  ```
- `Citation_X.txt` 或 `Citation_X.pdf` — 引用文本（X 为引用编号 1, 2, 3...）
  - 优先使用 `.txt`；如果只有 `.pdf`，系统会自动转换为 `.txt`

分析结果将写入 `papers/MyPaper/supervisor_analysis_report.json`。

---

## 🔌 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/health` | 健康检查 |
| GET  | `/api/tasks/<taskId>/analysis` | 获取分析结果 |
| POST | `/api/tasks/<taskId>/analyze` | 分析论文 |
| DELETE | `/api/tasks/<taskId>/analysis` | 删除分析结果 |
| GET  | `/api/papers/fuzzy_search` | 模糊检索论文 |
| POST | `/api/papers/download_citations` | 下载引文 |

---

## 🤝 多智能体工作流

```
                 ┌─────────────────────────┐
                 │     Supervisor Agent    │
                 │  (LangChain / LangGraph)│
                 └───────────┬─────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
    │ Citation Agent │ │ Sentiment Agent│ │ Retrieval Agent│
    │ 引用上下文分析 │ │ 情感判定       │ │ 论文 / 引文检索│
    └────────┬───────┘ └────────┬───────┘ └────────┬───────┘
             └──────────────────┼──────────────────┘
                                ▼
                ┌──────────────────────────────┐
                │   Supervisor 汇总 → 报告     │
                │  supervisor_analysis_report │
                └──────────────────────────────┘
```

---

## 📜 License

本项目采用 **MIT License** —— 详见 `LICENSE` 文件。

---

## 🙏 致谢

- [LangChain](https://www.langchain.com/) / [LangGraph](https://langchain-ai.github.io/langgraph/) —— 多智能体编排框架
- [OpenAI](https://openai.com/) / [OpenRouter](https://openrouter.ai/) —— 大模型接入
- [SerpApi](https://serpapi.com/) —— Google Scholar 数据源
- [Ant Design](https://ant.design/) —— UI 组件库

---

> 如果你觉得这个项目有帮助，欢迎 ⭐ Star 支持一下！你的鼓励是项目持续迭代的最大动力。
