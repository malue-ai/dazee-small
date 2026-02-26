---
name: bitwarden
description: Access and manage Bitwarden/Vaultwarden passwords via the bw CLI.
metadata:
  xiaodazi:
    dependency_level: external
    os: [common]
    backend_type: local
    user_facing: true
    bins: ["bw"]
---

# Bitwarden 密码管理

通过 Bitwarden CLI (`bw`) 安全访问密码库。

## 使用场景

- 用户说「帮我查一下 Netflix 的密码」「我的 WiFi 密码是什么」
- 用户说「生成一个强密码」

## 前置条件

安装 Bitwarden CLI：
```bash
# macOS
brew install bitwarden-cli
# Windows
winget install Bitwarden.CLI
# npm
npm install -g @bitwarden/cli
```

首次使用需登录：`bw login`

## 执行方式

### 解锁密码库

```bash
export BW_SESSION=$(bw unlock --raw)
```

### 搜索密码

```bash
bw list items --search "netflix" --session $BW_SESSION | python3 -c "
import json,sys
for item in json.load(sys.stdin):
    login = item.get('login', {})
    print(f\"Name: {item['name']}\")
    print(f\"Username: {login.get('username', 'N/A')}\")
    print(f\"Password: {login.get('password', 'N/A')}\")
    print('---')
"
```

### 生成密码

```bash
bw generate --length 20 --uppercase --lowercase --number --special
```

### 安全规则

- **绝不在聊天记录中保留密码明文**——展示后立即提醒用户已获取
- **不记录密码到日志或 MEMORY.md**
- 密码展示后建议用户使用剪贴板复制并清除

## 输出规范

- 搜索结果只显示账户名和用户名，密码需用户确认后才展示
- 展示密码时提醒「密码已显示，请及时复制并关闭对话」
- 密码库未解锁时引导用户执行 `bw unlock`
