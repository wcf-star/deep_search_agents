# deep_search_agents

> 基于 **DeepAgents + FastAPI + Vue** 的多智能体深度检索系统：1 个主智能体动态编排 3 个子智能体，接入**网络搜索 / 关系型数据库 / RAG 知识库**三类数据源，通过 **WebSocket** 实时推送全链路执行进度，并落地 **Markdown / PDF** 文档生成。

▶️ 演示视频](./11月18日.mp4)
<img width="2048" height="1180" alt="image" src="https://github.com/user-attachments/assets/4c01ace2-2fc9-446e-9c9f-71277b757697" />

## ✨ 功能特性

- **多智能体编排**：主智能体通过 `create_deep_agent(subagents=[...])` 注册 3 个子智能体，由 LLM 自主决策调用哪个子智能体，而非 if/else 硬编码。
  - 🕸️ 网络搜索助手（Tavily）
  - 🗄️ 数据库查询助手（MySQL，只读 SQL 白名单）
  - 📚 RAGFlow 知识库助手
- **实时进度推送**：WebSocket 按 `thread_id` 推送子智能体调用、工具调用、任务结果等全链路进度。
- **文档生成**：根据检索结果自动生成 Markdown，并可转 PDF（WeasyPrint，纯 Python，无需 Office）。
- **多轮对话持久化**：LangGraph `AsyncSqliteSaver`（SQLite checkpointer），服务重启后同 `thread_id` 可续聊。
- **文件上传 / 下载 / 浏览**：上传 md/txt/csv/docx/pdf/xlsx 文件供智能体读取，输出目录可在线浏览与下载。
- **安全加固**：SQL 注入防护、路径穿越防护、XSS 消毒、CORS 白名单、密钥隔离（`.env` / `.gitignore`）。
- **成本优化**：Tavily 搜索进程内 TTL 缓存，相同 query 在 TTL 内复用，降调用次数与延迟。

---

## 🏗️ 架构

```
                    ┌─────────────────────────────┐
                    │    Vue3 + Vite 前端 (5173)   │
                    │  聊天 / 文件 / 进度面板        │
                    └──────────────┬──────────────┘
                          HTTP/WS  │  REST + WebSocket
                    ┌──────────────▼──────────────┐
                    │     FastAPI 后端 (8000)      │
                    │  /api/task · /api/upload …   │
                    │  /ws/{thread_id} 进度推送     │
                    └──────────────┬──────────────┘
                                   │ create_deep_agent
                    ┌──────────────▼──────────────────────────────┐
                    │                主智能体 (main_agent)          │
                    │  动态编排 + 文档生成 (generate_markdown / pdf) │
                    └──┬───────────────┬────────────────┬──────────┘
          ┌────────────▼───┐  ┌────────▼───────┐  ┌─────▼──────────┐
          │ 网络搜索助手     │  │ 数据库查询助手  │  │ RAGFlow 助手   │
          │  Tavily API     │  │  MySQL(只读)   │  │ 内部知识库      │
          └────────────────┘  └────────────────┘  └────────────────┘
                                    │
                     LangGraph Checkpoint（SQLite 持久化会话）
```

---

## 🧰 技术栈

| 层 | 技术 |
| --- | --- |
| 后端框架 | FastAPI · Uvicorn · WebSocket · asyncio |
| Agent 框架 | DeepAgents · LangChain · LangGraph |
| 数据源 | Tavily（搜索）· MySQL（数据库）· RAGFlow（知识库） |
| 文档生成 | python-docx · pypdf · markdown · WeasyPrint |
| 前端 | Vue 3 · TypeScript · Vite（rolldown）· marked · DOMPurify |
| 持久化 | SQLite（langgraph-checkpoint-sqlite） |

---

## 📁 目录结构

```
deep_search_agents/
├── agent/                 # 主智能体 + 3 个子智能体定义
│   ├── main_agent.py      # 主智能体组装、流式执行、checkpointer
│   ├── llm.py             # LLM 初始化（OpenAI 兼容）
│   ├── prompts.py         # 加载 prompt/prompts.yml
│   └── subagents/         # 网络搜索 / 数据库查询 / RAGFlow 子智能体
├── api/                   # FastAPI 服务层
│   ├── server.py          # REST + WebSocket 接口
│   ├── monitor.py         # 进度上报 + WebSocket 连接管理
│   └── context.py         # ContextVar 会话上下文
├── tools/                 # 各类工具（搜索 / SQL / RAG / 文档 / 读文件）
├── utils/                 # 缓存 / 环境 / SQL 安全 / 路径 / PDF 转换
├── prompt/prompts.yml     # 主/子智能体的提示词配置
├── sql/company_data.sql   # 示例数据库（药品/库存/销售）
├── ui/                    # Vue3 前端
├── tests/                 # pytest 用例
├── docs/                  # 面试问答手册 / 代码地图
├── .env.example           # 环境变量模板
└── requirements.txt       # Python 依赖（版本已锁定）
```

---

## 🚀 快速开始

### 环境要求

- **Python 3.11**
- **Node.js ≥ 20.19**（前端 Vite/rolldown 需要；低于 20.19 会构建失败）
- **MySQL**（可选，仅数据库查询助手需要）
- 可用的 LLM（OpenAI 兼容，例如通义 Qwen）+ 对应的 API Key

### 1. 克隆仓库

```bash
git clone <your-repo-url>
cd deep_search_agents
```

### 2. 后端启动

```bash
# 创建并激活虚拟环境（Python 3.11）
python -m venv .venv311
# Windows
.venv311\Scripts\activate
# Linux / macOS
# source .venv311/bin/activate

# 安装依赖（版本已锁定，与开发环境一致）
pip install -r requirements.txt

# 配置环境变量
# Windows
copy .env.example .env
# Linux / macOS
# cp .env.example .env
# 编辑 .env，填入真实密钥（见下方「环境变量」）
```

启动后端（默认 `0.0.0.0:8000`）：

```bash
python -m api.server
# 或等价地
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 前端启动

```bash
cd ui
npm install
npm run dev
```

浏览器打开 **http://localhost:5173** 即可使用。

> 前端默认硬编码了后端地址 `http://localhost:8000`（REST）和 `ws://localhost:8000`（WebSocket），见 [ui/src/App.vue](ui/src/App.vue)。若后端不在 8000 端口，需同步修改。

### 4. 准备示例数据库（可选）

数据库查询助手依赖 MySQL，可用仓库自带的示例数据快速体验：

```bash
mysql -u root -p < sql/company_data.sql
```

该脚本会创建 `pharma_db` 数据库，包含药品信息（`drugs`）、库存（`inventory`）、销售记录（`sales_records`）三张表。随后在 `.env` 中把 `MYSQL_DATABASE` 设为 `pharma_db`。

---

## 🔑 环境变量

复制 `.env.example` 为 `.env` 并填写（`.env` 已被 `.gitignore` 排除，不会提交）：

| 变量 | 说明 |
| --- | --- |
| `LLM_QWEN_MAX` | LLM 模型名（OpenAI 兼容，例如 Qwen 的模型名） |
| `OPENAI_API_KEY` | LLM 的 API Key |
| `OPENAI_BASE_URL` | LLM 的 Base URL（OpenAI 兼容） |
| `TAVILY_API_KEY` | Tavily 联网搜索 Key |
| `RAGFLOW_API_URL` | RAGFlow 服务地址 |
| `RAGFLOW_API_KEY` | RAGFlow API Key |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | MySQL 连接配置 |
| `ALLOWED_ORIGINS` | 前端跨域白名单（逗号分隔） |
| `TAVILY_CACHE_TTL` | Tavily 搜索缓存 TTL（秒，默认 300） |

> ⚠️ **PDF 转换**依赖 WeasyPrint。Windows 下还需安装系统级 GTK3 运行时（`libgobject` / `libpango` 等 DLL），`utils/pdf_converter.py` 会在 import 前自动把 DLL 目录加入搜索路径。仅使用 Markdown 生成时不受影响。

---

## 🔌 API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/task` | 提交任务，返回 `thread_id`，后台异步执行 |
| `POST` | `/api/upload` | 上传文件（multipart，绑定 `thread_id`） |
| `GET` | `/api/download` | 下载输出目录内文件 |
| `GET` | `/api/files` | 列出输出目录内文件 |
| `WS` | `/ws/{thread_id}` | 订阅实时执行进度 |

---

## 🧪 测试

```bash
pip install -r requirements-dev.txt
pytest
```

测试覆盖缓存、checkpoint 持久化、ContextVar 会话上下文、路径解析、SQL 安全等模块（`tests/` 目录）。

---

## 🔐 安全设计

- **SQL 注入防护**：标识符白名单 + 反引号引用；自定义查询仅放行 `SELECT/SHOW/DESCRIBE/EXPLAIN/WITH`（只读），拒绝写操作。[utils/sql_safety.py](utils/sql_safety.py)
- **路径穿越防护**：上传取纯 basename + 扩展名白名单 + 大小上限；下载/列表反向校验 `is_relative_to(output_dir)`。[api/server.py](api/server.py)
- **XSS 防护**：前端 LLM 输出渲染前经 `DOMPurify.sanitize(marked(text))` 消毒。[ui/src/App.vue](ui/src/App.vue)
- **CORS 白名单**：避免 `allow_origins=["*"]` + `allow_credentials=True` 的无效组合。
- **密钥隔离**：`.env` 进 `.gitignore`，仓库仅保留 `.env.example` 模板。

---

## ⚠️ 已知限制 / 待办

- 持久化与缓存均采用**单进程**方案（SQLite / 进程内 TTL 缓存）；多 worker 部署时需替换为 `RedisSaver` / Redis 后端（接口不变）。
- 前端 `vite build` 生产构建需 Node ≥ 20.19。
- PDF 转换在 Windows 下依赖系统级 GTK3 运行时（见上方「环境变量」）。
- 目前未跑真实 LLM 的端到端全链路验证（重启续聊、三源联动）。
