# gpt_backend

基于 FastAPI 的 AI 对话站点后端，提供用户体系、流式对话、按量计费、支付回调、后台管理、公告/反馈/任务/软件下载等功能。

> 仓库中**不包含**任何真实密钥、证书、数据库备份或账号信息。所有敏感配置通过 `.env` 注入，见 [.env.example](.env.example)。

## 功能概览

| 模块 | 说明 |
| --- | --- |
| 用户 | 手机号/邮箱/用户名登录、注册、找回密码、匿名账号、API Key（`sk-`）管理 |
| 对话 | `POST /apiAI/user/gpt/ask` 流式返回，上下文记忆、token 计费、余额校验 |
| 计费 | 按供应商美元价 × 汇率 × 利润倍率 × 用户折扣/倍率计算，支持对话与图像 |
| 支付 | 支付宝异步通知、微信支付 v3、蓝兔支付（ltzf） |
| 后台 | 用户管理、公告、反馈、任务、软件分类与下载 |
| 文件 | 对话导出 docx/pptx，绘图结果落盘后通过 `/file` 下载 |
| 运营 | 邮件/短信验证码、每日定时任务、公告与软件展示 |

## 技术栈

- Python 3.10+
- FastAPI + Uvicorn/Gunicorn
- SQLAlchemy + PyMySQL（MySQL 8）
- Redis（会话 token、验证码、订单、临时上下文）
- APScheduler（每日任务）
- loguru（日志）
- pypandoc / pandoc（文档导出）

## 目录结构

```text
.
├── main_app.py            # 应用入口
├── app/                   # FastAPI 工厂、中间件、统一响应与异常
├── api/                   # 业务路由：users/chat/payment/admin/task/...
├── providers/chat/        # 对话供应商适配层
├── settings/
│   ├── env.py             # 环境变量统一读取
│   ├── macro.py           # 常量与业务参数
│   ├── billing.py         # 计费规则与模型价目
│   ├── database.py        # 数据库连接
│   └── dependencies.py    # DB / Redis 依赖
├── utils/                 # 日志、邮件、短信、支付、绘图、导出等工具
├── alembic/               # 数据库迁移
├── alembic.ini
├── start.sh               # gunicorn 启动脚本
├── requirements.txt
├── .env.example
└── .gitignore
```

`test/`、`docs/` 下的备份、`data_back/`、`开发文档/`、日志和证书均被 `.gitignore` 排除，仅保留在本地。

## 快速开始

### 1. 准备依赖服务

- MySQL 8：创建数据库 `gpt_db`
- Redis 6+
- pandoc：`apt install pandoc` 或 `brew install pandoc`

### 2. 安装 Python 依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

按需填写 `.env`。最关键的是：

```dotenv
DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/gpt_db
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
OPENAI_API_KEY=
SMTP_USER=
SMTP_PASSWORD=
```

证书类配置只填**文件路径**，不要填内容：

```dotenv
ALI_APP_PRIVATE_KEY_FILE=./secrets/alipay_app_private_key.txt
ALI_APP_PUBLIC_KEY_FILE=./secrets/alipay_public_key.txt
WXPAY_PRIVATE_KEY_FILE=/etc/security/apiclient_key.pem
```

未配置的第三方能力会在调用时明确报错（例如未配置 `SMTP_USER` 时发送邮件会提示），不会静默使用内置凭据。

### 4. 初始化数据库

```bash
alembic upgrade head
```

服务启动时也会自动创建业务表（`ensure_*_table`）。

### 5. 启动

开发：

```bash
python main_app.py          # 0.0.0.0:8888
```

生产：

```bash
./start.sh                  # gunicorn + UvicornWorker，0.0.0.0:8888
```

接口文档：<http://127.0.0.1:8888/docs>

## 接口分组

所有业务接口以 `/{NGINX_ROUTER}/user` 为前缀，默认 `/apiAI/user`。

| 前缀 | 说明 |
| --- | --- |
| `/verify` `/register` `/logout` | 登录、注册、登出 |
| `/password/send_code` `/password/reset` | 验证码与找回密码 |
| `/gpt/ask` | 对话主接口（需 `token` 请求头） |
| `/verify_pay` `/verify_rabbit` | 支付回调 |
| `/file` `/file/image` | 文件与图片下载 |
| `/feedback` `/announcement` `/software` | 反馈、公告、软件 |
| `/admin/*` | 后台管理（需管理员） |

## 环境变量说明

完整清单见 `.env.example`，常用项：

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy 连接串 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | Redis 连接 |
| `REDIS_DB_*` | 各业务模块使用的 db 编号 |
| `OPENAI_API_KEY` / `OPENAI_ORG_ID` | 上游模型凭据 |
| `OPENAI_PROXY` | 可选 HTTP 代理 |
| `LLM_PROXY_BASE` | 站内图像中转地址 |
| `SMTP_*` | 邮件验证码 |
| `SMS_APP_KEY` / `SMS_APP_SECRET` | 短信验证码 |
| `ALI_*` / `WXPAY_*` / `LTZF_*` | 支付配置 |
| `FILE_STORE_ADDR` / `FILE_STORE_LINUX_PWD` | 下载地址前缀与本地存储目录 |
| `SUPER_USER_ID_LIST` / `SUPER_ADMIN_PHONES` | 管理员白名单 |
| `DOCS_REFERERS` | 允许免登录访问 `/docs` 的来源 |

## 安全说明

- `.env`、证书、私钥、数据库备份、代理订阅、日志、开发文档与本地测试目录均已加入 `.gitignore`。
- 代码中的第三方凭据改为运行时读取，仓库内不保留真实值。
- 用户密码字段（`tb_user.password`）历史上为明文/简单摘要存储，迁移到强哈希前请勿直接用于新部署。
- 生产环境请务必关闭 `FastAPI(debug=True)`，并限制 CORS 的 `allow_origins`。
- 支付回调接口需要对签名进行校验后再落库。

## 许可证

未声明，默认保留所有权利。
