# gpt_backend

基于 FastAPI 的 AI 对话站点后端，提供用户体系、流式对话、按量计费、支付回调、后台管理、公告/反馈/任务/软件下载等功能。

> 仓库中**不包含**任何真实密钥、证书、数据库备份或账号信息。所有敏感配置通过 `.env` 注入，见 [.env.example](.env.example)。

## 功能概览

| 模块 | 说明 |
| --- | --- |
| 用户 | 手机号/邮箱/用户名登录、注册、找回密码、匿名账号、API Key（`sk-`）管理 |
| 对话 | `POST /apiAI/user/gpt/ask` 流式返回，上下文记忆、token 计费、余额校验 |
| 计费 | 按供应商美元价 × 汇率 × 利润倍率 × 用户折扣/倍率计算，支持对话与图像 |
| 支付 | 支付宝异步通知、微信支付 v3、蓝兔支付（ltzf）、虎皮椒（xunhupay） |
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
| `/verify_pay` `/verify_rabbit` | 支付回调（支付宝 / 蓝兔聚合） |
| `/wxpay/pay` `/wxpay/notify` `/wxpay/query` `/wxpay/status` | 微信支付 v3 直连 |
| `/xunhupay/pay` `/xunhupay/notify` `/xunhupay/query` `/xunhupay/status` | 虎皮椒个人微信/支付宝 |
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
| `ALI_*` / `WXPAY_*` / `LTZF_*` / `XUNHUPAY_*` | 支付配置 |

## 微信支付 v3 接入

项目同时保留两条支付链路，互不影响：

- `/pay_rabbit`、`/verify_rabbit`：旧的蓝兔聚合通道，继续可用。
- `/wxpay/*`：微信官方 APIv3 直连，当前支持 **Native 扫码** 与 **H5**。

### 1. 准备材料

从商户平台和证书包中取得：

| 材料 | 来源 |
| --- | --- |
| 商户号 `WXPAY_MCHID` | 证书文件名前缀，如 `1655833359_20261021_cert.zip` |
| 证书序列号 `WXPAY_CERT_SERIAL_NO` | `openssl x509 -in apiclient_cert.pem -noout -serial` |
| APIv3 密钥 `WXPAY_APIV3_KEY` | 商户平台「账户中心 → API 安全」自行设置的 32 位串 |
| 商户私钥 | 证书包里的 `apiclient_key.pem` |
| 微信支付公钥 | 商户平台「API 安全 → 微信支付公钥」，或证书包同目录的 `pub_key.pem` |
| 公钥 ID `WXPAY_PUBLIC_KEY_ID` | 商户平台公钥页面显示，形如 `PUB_KEY_ID_...` |

> `apiv2密钥` 与 `APIv3 密钥` 是两个不同的值。APIv2 只用于旧版接口和退款回调，
> 本项目 v3 链路**不使用**它，填错会导致回调解密失败。

### 2. 配置

```dotenv
WXPAY_MCHID=1655833359
WXPAY_CERT_SERIAL_NO=<40位十六进制>
WXPAY_APIV3_KEY=<32位>
WXPAY_APPID=<公众号或网站应用 appid>
WXPAY_NOTIFY_URL=https://your.domain/apiAI/user/wxpay/notify
WXPAY_PRIVATE_KEY_FILE=./weixin_pay/apiclient_key.pem
WXPAY_PUBLIC_KEY_FILE=./weixin_pay/pub_key.pem
WXPAY_PUBLIC_KEY_ID=PUB_KEY_ID_xxxxxxxx
WXPAY_PARTNER_MODE=false
```

证书与密钥目录（`weixin_pay/`、`*.pem`）已在 `.gitignore` 中，不会进入仓库。

### 3. 接口

```bash
# 配置自检，部署后先跑这个
curl http://127.0.0.1:9000/apiAI/user/wxpay/status

# 下单：pay_type 可选 native / h5
curl -X POST http://127.0.0.1:9000/apiAI/user/wxpay/pay \
  -H 'Content-Type: application/json' -H 'token: <登录 token>' \
  -d '{"userId":1,"money":50,"function_code":"chatGpt","pay_type":"native"}'

# 查单
curl http://127.0.0.1:9000/apiAI/user/wxpay/query/<outTradeNo>
```

回调地址必须能被微信公网访问，本地调试请用内网穿透工具映射到同一路径。

### 4. 联调建议

先用独立端口试跑，确认无误后再替换旧链路：

```bash
APP_PORT=9000 python main_app.py
```

`main_app.py` 已支持 `APP_PORT`，默认仍是 8888。
| `FILE_STORE_ADDR` / `FILE_STORE_LINUX_PWD` | 下载地址前缀与本地存储目录 |
| `SUPER_USER_ID_LIST` / `SUPER_ADMIN_PHONES` | 管理员白名单 |
| `DOCS_REFERERS` | 允许免登录访问 `/docs` 的来源 |

## 虎皮椒支付接入

第三条支付链路，适合个人开发者（无需营业执照），与蓝兔、微信 v3 并存。
协议文档：<https://www.xunhupay.com/doc/api/pay.html>
前端对接文档：[`docs/前端对接-虎皮椒支付.md`](docs/前端对接-虎皮椒支付.md)

### 1. 配置

```dotenv
XUNHUPAY_APPID=201906188998
XUNHUPAY_APPSECRET=<虎皮椒后台的密钥>
XUNHUPAY_GATEWAY=https://api.xunhupay.com/payment/do.html
XUNHUPAY_NOTIFY_URL=https://your.domain/apiAI/user/xunhupay/notify
XUNHUPAY_RETURN_URL=https://your.domain/
XUNHUPAY_WAP_URL=https://your.domain
XUNHUPAY_WAP_NAME=your-site-name
```

`XUNHUPAY_WAP_NAME` 为网站名称，手机 H5 通道必填；PC 扫码通道不需要。
`XUNHUPAY_QUERY_URL` 留空时自动取网关同域的 `/payment/query.html`。

### 2. 接口

```bash
# 配置自检
curl http://127.0.0.1:9000/apiAI/user/xunhupay/status

# 下单：pay_type=auto 按 UA 分流，h5 强制手机，qrcode 强制 PC
curl -X POST http://127.0.0.1:9000/apiAI/user/xunhupay/pay \
  -H 'Content-Type: application/json' -H 'token: <登录 token>' \
  -d '{"userId":1,"money":50,"function_code":"chatGpt","pay_type":"auto"}'

# 查单
curl http://127.0.0.1:9000/apiAI/user/xunhupay/query/<outTradeNo>
```

响应中 `payUrl` 在 `payType=h5` 时是可跳转链接，在 `payType=qrcode` 时是
可直接展示的二维码图片地址。

### 3. 回调

`notify_url` 收到 form 表单 POST，验签通过且 `status=OD` 才入账，
处理成功必须返回纯文本 `success`，否则虎皮椒会重试 6 次。

- 签名规则：去 `hash` 与空值，按参数名 ASCII 升序拼 `k=v&k=v`，末尾直接追加
  APPSECRET，取 32 位小写 MD5。
- 下单时会记录金额，回调金额不一致直接拒绝。
- 入账幂等、订单号解析复用 `utils/pay_util/pay_settle.py`。
- **金额只接受大于 0 的整数元**；`token` 即人民币余额，充多少加多少
  （`utils/pay_util/xunhupay/settle.py`）。

## 安全说明

- `.env`、证书、私钥、数据库备份、代理订阅、日志、开发文档与本地测试目录均已加入 `.gitignore`。
- 代码中的第三方凭据改为运行时读取，仓库内不保留真实值。
- 用户密码字段（`tb_user.password`）历史上为明文/简单摘要存储，迁移到强哈希前请勿直接用于新部署。
- 生产环境请务必关闭 `FastAPI(debug=True)`，并限制 CORS 的 `allow_origins`。
- 支付回调接口需要对签名进行校验后再落库。

## 许可证

未声明，默认保留所有权利。
