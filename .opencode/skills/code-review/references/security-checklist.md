# 安全检查清单

检视时按此表逐项扫一遍**变更部分**。只报"本次变更引入或加剧"的问题。

## 1. 注入

| 类型 | 危险信号 | 正确做法 |
|---|---|---|
| SQL | 字符串拼接查询、f-string 拼 SQL | 参数化查询 / ORM 绑定 |
| 命令 | `shell=True`、`os.system`、`eval`、拼接后 `exec` | 传数组参数、白名单校验 |
| 模板 | 用户输入进 `render_template_string`、`innerHTML` | 转义 / 只用模板变量 |
| 日志 | 用户输入直接进日志格式串 | 用参数化日志 |

## 2. 认证与授权

- 新增接口是否**真的**校验了身份？（很多漏洞是"加了路由但忘了加鉴权装饰器"）
- 授权是否**基于资源归属**校验，而不只校验"已登录"（水平越权）
- 敏感操作是否有二次确认 / 幂等保护

## 3. 敏感数据

- 硬编码密钥、token、密码（含注释里的示例值）
- 密钥是否随日志、异常信息、响应体泄露
- 密码是否明文比较 / 弱哈希（应为 bcrypt/argon2/scrypt）

## 4. 路径与文件

- `open(用户输入)`、`os.path.join(base, 用户输入)` 未做 basename + realpath 前缀校验
- 上传文件未限制类型/大小/存放位置
- 解压未防 zip slip（`../` 逃逸）

## 5. 反序列化与解析

- `pickle.loads`、`yaml.load`（非 safe_load）、Java 原生反序列化、`eval` 解析用户数据
- JSON/XML 解析未限制深度或大小（XXE、billion laughs）

## 6. 依赖与供应链

- 新增依赖是否**真实存在于官方 registry**（防幻觉包名 / 抢注）
- 版本是否精确锁定，是否引入已知 CVE
- 是否从非官方源、URL、git 分支安装

## 7. 加密与随机

- 用 `random` 生成 token/密钥（应为 `secrets` / `crypto.randomBytes`）
- 自造加密算法、ECB 模式、固定 IV
- 关闭 TLS 校验（`verify=False`、`InsecureSkipVerify`）

## 8. 默认配置

- 调试模式、详细错误、CORS 通配符、默认口令是否被带上生产
- 权限默认应为拒绝（allowlist），而非默认放行（denylist）
