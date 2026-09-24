# CiteScope 引用视界 · 前端

CiteScope 引用视界的前端界面，基于 React + Vite + Ant Design 构建。

## 项目结构

```
client/
├── src/
│   ├── pages/              # 页面组件
│   │   ├── WelcomePage.jsx          # 欢迎页
│   │   ├── TaskManagementPage.jsx   # 任务管理页
│   │   └── CitationAnalysisPage.jsx # 引用分析页
│   ├── App.jsx             # 主应用组件
│   ├── main.jsx            # 入口文件
│   └── *.css               # 样式文件
├── index.html              # HTML模板
├── package.json            # 依赖配置
└── vite.config.js          # Vite配置
```

## 安装依赖

```bash
cd client
npm install
```

## 启动开发服务器

```bash
npm run dev
```

前端服务将在 `http://localhost:3000` 启动。

## 构建生产版本

```bash
npm run build
```

构建产物将输出到 `dist/` 目录。

## API 接口

前端通过 Vite 代理访问后端 API：

- 开发环境：`/api/*` → `http://localhost:5000/api/*`
- 生产环境：需要配置反向代理或直接访问后端API

### 主要API端点

- `GET /api/tasks/<taskId>/analysis` - 获取分析结果
- `POST /api/tasks/<taskId>/analyze` - 分析论文
- `DELETE /api/tasks/<taskId>/analysis` - 删除分析结果
- `GET /api/health` - 健康检查

## 注意事项

1. **后端服务**：确保后端服务（`app.py`）正在运行在 `http://localhost:5000`
2. **CORS配置**：后端已配置CORS，允许前端跨域访问
3. **Task ID映射**：当前实现中，`taskId` 直接对应后端的 `paper_id`

## 开发说明

- 使用 React 18 + Hooks
- UI框架：Ant Design 5
- 路由：React Router v6
- 构建工具：Vite 5


