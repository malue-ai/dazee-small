---
name: privacy-auditor
description: Scan for privacy risks on the local system - exposed credentials, overly permissive files, tracking cookies, and sensitive data in public directories.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 隐私审计

帮助用户扫描本地系统的隐私风险：暴露的凭证、权限过大的文件、敏感数据泄露。

## 使用场景

- 用户说「帮我检查一下电脑有没有安全隐患」「扫描隐私风险」
- 用户说「检查有没有密码明文存储」「敏感文件权限对不对」
- 用户说「我要清理浏览器的追踪数据」

## 执行方式

通过 bash 命令扫描本地文件系统，检查常见隐私风险。

### 1. 检查暴露的凭证

```bash
# 搜索可能包含密码/密钥的文件（仅检查文件名，不读取内容）
find ~ -maxdepth 3 -type f \( \
  -name "*.pem" -o -name "*.key" -o -name "*.env" \
  -o -name "credentials*" -o -name "*.keystore" \
  -o -name "id_rsa" -o -name "id_ed25519" \
\) 2>/dev/null
```

### 2. 检查 SSH 密钥权限

```bash
# SSH 密钥应为 600，目录应为 700
ls -la ~/.ssh/ 2>/dev/null

# 检查权限是否正确
stat -f "%Sp %N" ~/.ssh/* 2>/dev/null || stat -c "%A %n" ~/.ssh/* 2>/dev/null
```

### 3. 检查公共目录中的敏感文件

```bash
# Desktop 和 Downloads 中的敏感文件
find ~/Desktop ~/Downloads -maxdepth 2 -type f \( \
  -name "*.csv" -o -name "*.xls*" -o -name "*.sql" \
  -o -name "*.bak" -o -name "*.dump" \
\) 2>/dev/null | head -20
```

### 4. 检查浏览器数据

```bash
# Chrome cookies/history 大小
du -sh ~/Library/Application\ Support/Google/Chrome/Default/Cookies 2>/dev/null
du -sh ~/Library/Application\ Support/Google/Chrome/Default/History 2>/dev/null

# Firefox
du -sh ~/Library/Application\ Support/Firefox/Profiles/*/cookies.sqlite 2>/dev/null
```

### 5. 检查最近访问的敏感文件

```bash
# macOS 最近打开的文件
ls -lt ~/Library/Recent\ Documents/ 2>/dev/null | head -10

# 最近修改的大文件
find ~ -maxdepth 3 -type f -mtime -7 -size +10M 2>/dev/null | head -20
```

### 审计报告

```markdown
## 隐私审计报告

**扫描时间**: YYYY-MM-DD HH:MM
**扫描范围**: 用户主目录

### 风险等级汇总
- 🔴 高风险: X 项
- 🟡 中风险: X 项
- 🟢 低风险/信息: X 项

### 详细发现

#### 🔴 高风险
| 发现 | 位置 | 建议 |
|---|---|---|
| SSH 私钥权限过大 | ~/.ssh/id_rsa (644) | 修改为 600 |

#### 🟡 中风险
| 发现 | 位置 | 建议 |
|---|---|---|
| .env 文件在公共目录 | ~/Desktop/.env | 移到安全位置 |

#### 修复建议
1. [具体修复命令]
```

## 安全规则

- **只检查文件名和权限，不读取文件内容**
- **不修改任何文件**：只报告风险，修复需用户确认
- **扫描结果不持久化**：报告展示后不存储到磁盘
- **不扫描其他用户目录**：只扫描当前用户的 HOME

## 输出规范

- 按风险等级排序展示
- 每个风险附带一键修复命令
- 修复命令需用户通过 HITL 确认后执行
