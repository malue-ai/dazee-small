---
name: medication-tracker
description: Track medication schedules, set reminders, and provide basic drug information lookup. Not a substitute for medical advice.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 用药管理与提醒

帮助用户记录和管理药物服用情况，设置提醒，查询基本药物信息。

## 使用场景

- 用户说「帮我记一下每天要吃的药」「提醒我晚上 8 点吃药」
- 用户需要管理多种药物的服用时间
- 用户想查询某种药的基本信息

## 药单管理

### 数据存储

```bash
# 药单存储路径
mkdir -p ~/.xiaodazi/medication

# 药单格式
cat > ~/.xiaodazi/medication/prescriptions.json << 'EOF'
{
  "medications": [
    {
      "name": "阿托伐他汀钙片",
      "dosage": "20mg",
      "frequency": "每日一次",
      "time": "21:00",
      "notes": "睡前服用，避免与葡萄柚同食",
      "started": "2025-01-15",
      "prescriber": "心内科 王医生"
    }
  ],
  "updated_at": "2025-02-07"
}
EOF
```

### 添加药物

用户口述后，LLM 结构化写入药单。

### 查看药单

```bash
cat ~/.xiaodazi/medication/prescriptions.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('medications', []):
    print(f'💊 {m[\"name\"]} {m[\"dosage\"]}')
    print(f'   频率: {m[\"frequency\"]}，时间: {m[\"time\"]}')
    if m.get('notes'):
        print(f'   注意: {m[\"notes\"]}')
    print()
"
```

### 服药记录

```bash
# 记录服药
cat >> ~/.xiaodazi/medication/log_$(date +%Y-%m).json << EOF
{"date": "$(date +%Y-%m-%d)", "time": "$(date +%H:%M)", "medication": "阿托伐他汀钙片", "taken": true}
EOF
```

## 提醒机制

配合 `macos-notification` / `windows-notification` / `linux-notification` 发送提醒：

```bash
# macOS 提醒示例
osascript -e 'display notification "该服用阿托伐他汀钙片 20mg 了" with title "小搭子 · 用药提醒" sound name "default"'
```

## 药物信息查询（OpenFDA API，免费）

```bash
# 按药名查询
curl -s "https://api.fda.gov/drug/label.json?search=openfda.brand_name:atorvastatin&limit=1" | python3 -c "
import json, sys
data = json.load(sys.stdin)
result = data.get('results', [{}])[0]
print(f'药品: {result.get(\"openfda\", {}).get(\"brand_name\", [\"?\"])[0]}')
print(f'用途: {result.get(\"indications_and_usage\", [\"?\"])[0][:200]}...')
print(f'警告: {result.get(\"warnings\", [\"?\"])[0][:200]}...')
"
```

## 安全规则

- **免责声明**：每次回复药物信息时注明「仅供参考，请遵医嘱」
- **不做诊断**：不判断用户症状，不推荐药物
- **不建议停药/换药**：这类操作必须咨询医生
- 药单数据仅存储在本地，不上传
