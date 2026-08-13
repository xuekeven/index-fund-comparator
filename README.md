# 指数基金比较工具

当前版本采用前后端分离架构：

- 前端：Vite、React、TypeScript
- 后端：FastAPI、Pydantic、SQLAlchemy 2
- 数据库：PostgreSQL 16、Alembic
- 数据：支持 PostgreSQL Repository；测试环境继续使用内存样例 Repository

## 本地启动

后端：

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
pnpm install
pnpm dev
```

访问地址：

- Web：http://127.0.0.1:3000

这是个人自用版本，FastAPI 的 Swagger、ReDoc 和 OpenAPI schema 默认关闭。

如需修改 API 地址，将 `frontend/.env.example` 复制为 `frontend/.env.local`，再设置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

## 数据库与迁移

将 `backend/.env.example` 复制为 `backend/.env`，配置 PostgreSQL 连接：

```env
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/index_fund_comparator
IFC_DATA_MODE=database
```

也兼容不带驱动名的 `postgresql://...` 写法，后端会统一使用 `psycopg`。

首次建表或更新到最新结构：

```bash
cd backend
.venv/bin/alembic upgrade head
```

检查当前版本和 ORM 模型是否与数据库一致：

```bash
.venv/bin/alembic current
.venv/bin/alembic check
```

修改 `app/database_models.py` 后生成下一版迁移：

```bash
.venv/bin/alembic revision --autogenerate -m "describe schema change"
```

生成后应先审查 `migrations/versions` 中的迁移文件，再执行 `upgrade head`。当前核心表包括指数定义、基金主体、份额类别、ETF 上市信息、费率历史、净值、行情、基准、规模、销售限额、计算指标和来源文档。迁移只创建结构，不写入开发样例数据。

同步沪深交易所官方 ETF 清单、上交所官方展示规模和日行情：

```bash
cd backend
.venv/bin/python -m app.sync.sse_funds --dry-run
.venv/bin/python -m app.sync.sse_funds
.venv/bin/python -m app.sync.sse_quotes --dry-run
.venv/bin/python -m app.sync.sse_quotes
.venv/bin/python -m app.sync.szse_funds --dry-run
.venv/bin/python -m app.sync.szse_funds
.venv/bin/python -m app.sync.szse_quotes --dry-run
.venv/bin/python -m app.sync.szse_quotes
```

同步命令可重复执行。日行情命令默认查找最近一个有数据的交易日，也可传入 `--date YYYY-MM-DD`。当前已适配上交所、深交所 ETF 清单及日行情。深交所清单中的当前规模单位是万份，因此不会误写成以人民币计价的基金规模；深交所日行情仅落库官方提供的收盘价和成交金额，不推测开高低、成交量或净值。场外份额和基金净值将在对应官方来源适配器完成后补齐。

## 验证

```bash
cd frontend
pnpm lint
pnpm build

cd ../backend
.venv/bin/pytest -q
.venv/bin/alembic check
```

## Home Server 部署（Git + PM2）

以下方案直接使用 PM2 托管 FastAPI 和前端静态文件，不依赖 Docker。示例假设服务器为 Linux，已安装 Git、Python 3.11+、Node.js 20+、pnpm、PM2 和 PostgreSQL。

首次拉取代码：

```bash
git clone git@github.com:xuekeven/index-fund-comparator.git
cd index-fund-comparator
```

准备后端：

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
```

编辑 `backend/.env`。把 `YOUR_SERVER_IP` 替换为浏览器实际访问 Home Server 使用的局域网 IP、Tailscale IP 或域名：

```env
DATABASE_URL=postgresql+psycopg://username:password@127.0.0.1:5432/index_fund_comparator
IFC_DATA_MODE=database
IFC_CORS_ORIGINS=http://YOUR_SERVER_IP:3000
```

执行数据库迁移：

```bash
.venv/bin/alembic upgrade head
cd ..
```

安装并构建前端。`VITE_API_BASE_URL` 是构建时配置，必须是使用者浏览器能够访问到的后端地址：

```bash
cd frontend
pnpm install --frozen-lockfile
VITE_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1 pnpm build
cd ..
```

启动并设置开机自启：

```bash
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup
```

`pm2 startup` 会输出一条需要以管理员权限执行的命令；执行该命令后再次运行 `pm2 save`。完成后访问 `http://YOUR_SERVER_IP:3000`。查看运行状态和日志：

```bash
pm2 status
pm2 logs index-fund-api
pm2 logs index-fund-web
```

后续发布新版本：

```bash
cd index-fund-comparator
git pull --ff-only

cd backend
.venv/bin/pip install -e .
.venv/bin/alembic upgrade head
cd ../frontend
pnpm install --frozen-lockfile
VITE_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1 pnpm build
cd ..

pm2 startOrReload ecosystem.config.cjs
pm2 save
```

如果服务只供自己使用，建议仅通过家庭局域网或 Tailscale 开放 `3000`、`8000` 端口；不要把 PostgreSQL 的 `5432` 端口直接暴露到公网。若以后绑定公网域名，应在 PM2 前增加 Caddy 或 Nginx，并启用 HTTPS。

下一步接入基金管理人或基金公告来源，补齐 ETF 每日净值、管理费、托管费和人民币资产规模；之后再接入普通场外指数基金及 ETF 联接基金份额。前端接口协议无需修改。
