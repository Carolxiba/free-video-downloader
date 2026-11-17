# 用户账号与登录

拾帧现在要求用户注册并登录后才能解析视频、创建下载任务或生成 AI 摘要。

## 安全设计

- 用户名长度为 3-32 位，密码长度为 8-128 位。
- 密码通过 `scrypt` 加盐哈希后保存，数据库不保存明文密码。
- 登录成功后签发随机服务端会话令牌，浏览器只保存 `HttpOnly`、`SameSite=Lax` Cookie。
- 数据库仅保存令牌的 SHA-256 摘要，不保存原始令牌。
- 下载任务和摘要任务均绑定用户，其他账号无法轮询、取消或下载。
- 注册和登录接口按来源 IP 限制为每分钟 10 次。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FZ_AUTH_DB_PATH` | `.runtime/auth.db` | SQLite 用户和会话数据库 |
| `FZ_AUTH_SESSION_TTL_SECONDS` | `604800` | 会话有效期 |
| `FZ_AUTH_COOKIE_SECURE` | `false` | 使用 HTTPS 部署时应启用 |

如需公网部署，请设置：

```powershell
$env:FZ_AUTH_COOKIE_SECURE = "true"
$env:FZ_AUTH_DB_PATH = "D:\shizhen-data\auth.db"
```

## 接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/api/auth/register` | 创建账号并自动登录 |
| `POST` | `/api/auth/login` | 登录 |
| `POST` | `/api/auth/logout` | 删除当前会话 |
| `GET` | `/api/auth/me` | 读取当前登录用户 |

健康检查保持匿名可访问；解析、下载和摘要接口都要求有效登录会话。
