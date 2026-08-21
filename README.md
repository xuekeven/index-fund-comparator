# 指数基金比较工具

当前版本开发时采用前后端分离架构，生产环境由 FastAPI 单进程同时提供 API 和构建后的前端静态文件：

- 前端：Vite、React、TypeScript
- 后端：FastAPI、Pydantic、SQLAlchemy 2
- 数据库：PostgreSQL 16、Alembic
- 数据：支持 PostgreSQL Repository；测试环境继续使用内存样例 Repository

本项目不区分本地开发库和服务器生产库。PostgreSQL 运行在 Home Server 上，是唯一共享数据库；服务器后端通过回环地址连接，本地后端通过 Tailscale 或可信局域网连接同一实例。数据库迁移和正式数据同步统一在 Home Server 执行，避免两端重复迁移或同时写入。

当前 Web 端支持按指数和交易方式筛选基金、搜索基金，并选择 2–4 个份额生成并排比较结果；指数、场内/场外及其下级筛选会保存在浏览器 `localStorage`。比较表展示精确跟踪基准、交易价格与净值日期、运作费率、销售服务费、收益率、规模及数据来源；暂无数据的指标明确显示为空。

## 目录

- [本地启动](#本地启动)
- [共享数据库与迁移](#共享数据库与迁移)
  - [连接方式](#连接方式)
  - [迁移规则](#迁移规则)
  - [数据同步规则](#数据同步规则)
- [验证](#验证)
- [Home Server 部署（Git + PM2）](#home-server-部署git--pm2)

## 本地启动

首次启动前，先按[共享数据库与迁移](#共享数据库与迁移)配置 `backend/.env`，确保本地后端连接 Home Server 上的共享 PostgreSQL。本地启动命令不会自动执行数据库迁移。

后端：

```bash
cd backend
uv sync --extra dev --locked
uv run uvicorn app.main:app --reload --port 7006
```

前端：

```bash
cd frontend
pnpm install
pnpm dev
```

访问地址：

- Web：http://127.0.0.1:6006/indexfund/

这是个人自用版本，FastAPI 的 Swagger、ReDoc 和 OpenAPI schema 默认关闭。

Vite 会把 `/indexfund/api/*` 代理到本地 FastAPI `7006`。如需覆盖 API 地址，将 `frontend/.env.example` 复制为 `frontend/.env.local`，再设置：

```env
VITE_API_BASE_URL=/indexfund/api/v1
```

## 共享数据库与迁移

### 连接方式

将 `backend/.env.example` 复制为 `backend/.env`。本地开发环境使用 Home Server 的 Tailscale 域名、Tailscale IP 或可信局域网 IP：

```env
DATABASE_URL=postgresql+psycopg://username:password@YOUR_HOME_SERVER:5432/index_fund_comparator
IFC_DATA_MODE=database
IFC_CORS_ORIGINS=http://localhost:6006,http://127.0.0.1:6006
```

Home Server 上的后端连接同一个数据库，但使用本机回环地址：

```env
DATABASE_URL=postgresql+psycopg://username:password@127.0.0.1:5432/index_fund_comparator
IFC_DATA_MODE=database
IFC_CORS_ORIGINS=http://YOUR_SERVER_IP:6006
```

两份配置中的数据库名、用户和数据内容相同，只有主机地址不同。也兼容不带驱动名的 `postgresql://...` 写法，后端会统一使用 `psycopg`。

共享数据库必须只通过 Tailscale 或可信局域网访问，不要将 PostgreSQL `5432` 暴露到公网。PostgreSQL 的 `listen_addresses` 和 `pg_hba.conf` 应只允许服务器回环地址及明确授权的本地设备地址。

### 迁移规则

共享数据库只有一套 schema，因此迁移不能在本地启动流程中自动执行。约定如下：

- 正式迁移只在 Home Server 发布代码时执行一次；
- 本地开发前先拉取最新代码，确认本地 ORM 与共享数据库版本一致；
- 修改数据库模型后先生成并审查迁移文件，发布前备份共享数据库；
- 不同时在本地和服务器执行 `alembic upgrade head`；
- 自动化测试固定使用内存样例 Repository，不读写共享数据库。

在 Home Server 首次建表或发布新版本时执行：

```bash
cd backend
uv run alembic upgrade head
```

任一环境可以只读检查当前迁移版本；`alembic check` 会连接共享数据库并比较 ORM 模型：

```bash
uv run alembic current
uv run alembic check
```

修改 `app/database_models.py` 后，在开发机生成下一版迁移：

```bash
uv run alembic revision --autogenerate -m "describe schema change"
```

生成后应先审查 `migrations/versions` 中的迁移文件并提交代码，发布时再在 Home Server 执行 `upgrade head`。当前核心表包括指数定义、基金主体、份额类别、ETF 上市信息、费率历史、净值、行情、基准、规模、销售限额、计算指标和来源文档。迁移只创建结构，不写入开发样例数据。

### 数据同步规则

正式同步任务只在 Home Server 执行。本地环境直接读取同步后的共享数据，不再运行第二套定时任务。需要开发或排查采集器时，先使用 `--dry-run`；只有确认不会影响共享数据后，才执行正式同步。

Home Server 的同步时间由 `deploy/schedules.conf` 管理，并通过 `deploy/manage-crontab.sh` 幂等安装到部署用户的 crontab。安装脚本只替换带项目标记的任务以及旧版同名同步命令，不会覆盖该用户的其他定时任务。

各官方数据源、同步脚本、字段转换和筛选规则见[基金数据来源](./数据来源.md)。

在 Home Server 同步沪深交易所官方 ETF 清单、上交所官方展示规模、管理费率、托管费率、单位净值和日行情：

```bash
cd backend
uv run python -m app.sync.sse_funds --dry-run
uv run python -m app.sync.sse_funds
uv run python -m app.sync.sse_details --dry-run
uv run python -m app.sync.sse_details
uv run python -m app.sync.szse_funds --dry-run
uv run python -m app.sync.szse_funds
uv run python -m app.sync.szse_details --dry-run
uv run python -m app.sync.szse_details
uv run python -m app.sync.csrc_funds --dry-run
uv run python -m app.sync.csrc_funds
```

同步命令可重复执行，但仍应避免本地和服务器同时运行。上交所脚本 A 与深交所脚本 C 每周更新基金列表和目标基金主数据；深交所脚本 C 同时从证监会最新基金产品资料概要提取管理费与托管费。上交所脚本 B 在交易日收盘后更新收盘价、净值、费率、规模、交易日和五个区间收益率；深交所脚本 D 只更新每日收盘价、正式净值、估算规模、交易日和五个区间收益率，不重复下载费率 PDF。深交所基金规模按同日“万份”规模乘以同日单位净值估算，质量状态标记为 `estimated`，日期不一致时不写入。证监会场外同步器会排除 ETF、LOF、指数增强和等权/质量/低波等非目标指数变体，并按官方产品 ID 合并 A/C/E 等份额。运作费率采用管理费与托管费之和，销售服务费单列；仅当收盘价与单位净值日期一致时计算同日估算偏离。

## 验证

```bash
cd frontend
pnpm test
pnpm lint
pnpm build

cd ../backend
uv run pytest -q
uv run alembic check
```

## Home Server 部署（Git + PM2）

以下方案由 PM2 托管一个 FastAPI/Uvicorn 进程。FastAPI 在 `127.0.0.1:6006` 同时提供 API 和构建后的前端静态文件，Nginx 通过 `/indexfund/` 反向代理；生产环境不运行 Vite 静态服务器。示例假设 Home Server 为 Linux，已安装 Git、uv、Python 3.11+、Node.js 20+、pnpm、PM2、Nginx 和 PostgreSQL 16。

首次拉取代码：

```bash
git clone git@github.com:xuekeven/index-fund-comparator.git
cd index-fund-comparator
```

准备后端：

```bash
cd backend
uv sync --locked
cp .env.example .env
cd ..
```

编辑服务器上的 `backend/.env`。数据库位于同一台 Home Server，因此后端使用 `127.0.0.1`；把 `YOUR_SERVER_IP` 替换为浏览器实际访问 Home Server 使用的局域网 IP、Tailscale IP 或域名：

```env
DATABASE_URL=postgresql+psycopg://username:password@127.0.0.1:5432/index_fund_comparator
IFC_DATA_MODE=database
IFC_CORS_ORIGINS=https://homeserver.tailed5977.ts.net
```

安装数据同步定时任务。当前配置为脚本 A/C 每周一 `09:00`、脚本 B/D 周一至周五 `16:00`，时区为 `Asia/Shanghai`：

```bash
./deploy/manage-crontab.sh print
./deploy/manage-crontab.sh install
crontab -l
```

默认日志写入当前部署用户的 `~/logs/index-fund-sync.log`。如需使用其他位置，在安装时设置 `IFC_SYNC_LOG`；该值会以绝对路径写入 crontab：

```bash
IFC_SYNC_LOG=/path/to/index-fund-sync.log ./deploy/manage-crontab.sh install
```

首次部署前确认本地开发机已能通过 Tailscale 或可信局域网连接该 PostgreSQL 实例。服务器至少需要满足：

- 已创建 `index_fund_comparator` 数据库及专用用户；
- 服务器后端可通过 `127.0.0.1:5432` 连接；
- 本地设备只能通过 Tailscale 或可信局域网连接；
- 防火墙不向公网开放 `5432`；
- 已配置数据库定期备份。

首次部署或包含迁移的发布，先备份共享数据库，再在 Home Server 执行迁移：

```bash
mkdir -p ../index-fund-comparator-backups
pg_dump \
  --format=custom \
  --file="../index-fund-comparator-backups/index_fund_comparator_$(date +%Y%m%d_%H%M%S).dump" \
  --dbname=postgresql://username@127.0.0.1:5432/index_fund_comparator

cd backend
uv run alembic upgrade head
cd ..
```

`pg_dump` 会按 PostgreSQL 客户端配置提示输入密码，也可以在服务器上使用权限受控的 `.pgpass`。上述目录位于 Git 仓库之外，备份还应定期转移到独立存储。

安装并构建前端。默认使用同源 API 地址 `/indexfund/api/v1`，无需写死服务器地址：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
```

启动并设置开机自启：

```bash
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup
```

`pm2 startup` 会输出一条需要以管理员权限执行的命令；执行该命令后再次运行 `pm2 save`。完成后访问 `https://homeserver.tailed5977.ts.net/indexfund/`。查看运行状态和日志：

```bash
pm2 status
pm2 logs index-fund-api
```

后续发布新版本：

```bash
cd index-fund-comparator
git pull --ff-only

cd backend
uv sync --locked
uv run alembic current
uv run alembic upgrade head
cd ..
./deploy/manage-crontab.sh install
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..

pm2 startOrReload ecosystem.config.cjs
pm2 save
```

如果本次发布不包含新的 Alembic 迁移，`upgrade head` 不会修改数据库。若包含迁移，应先停止写入型同步任务并完成备份，再升级 schema 和重载服务。不要在本地开发机重复执行同一迁移。

定时任务修改后只需更新 `deploy/schedules.conf` 并重新执行安装脚本。卸载项目定时任务使用 `./deploy/manage-crontab.sh remove`；该命令不会删除其他 crontab 条目。

FastAPI 只监听回环地址 `127.0.0.1:6006`，对外仅开放 Nginx HTTPS 的 `/indexfund/`。开发端口 `7006` 不用于生产。PostgreSQL 的 `5432` 仅对服务器自身和明确授权的 Tailscale/局域网设备开放，绝不能直接暴露到公网。

下一步补齐场外基金费率、人民币资产规模和区间收益率。沪深场内基金已经分别通过脚本 B/D 计算五个区间收益率；深交所新部署实例需要等待正式净值逐日积累后才会逐步出现长周期收益率。
