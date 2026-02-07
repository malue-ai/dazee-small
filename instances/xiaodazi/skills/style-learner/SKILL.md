---
name: style-learner
description: Learn and memorize user writing style from conversation history and sample texts. Applies learned style to future writing tasks.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 风格学习

从用户的对话和文本样本中学习写作风格，并在后续写作任务中复用。

## 使用场景

- 用户说「记住我的写作风格」「用我的风格写一篇 XXX」
- 用户提供了几篇自己的文章作为样本
- 小搭子主动识别到用户有稳定的写作偏好

## 工作流程

### 阶段 1：采集样本

当用户提供文本样本时，提取风格特征：

```
输入：用户的 1-3 篇文本样本
  ↓
分析维度：
  - 语气：正式/半正式/口语/学术
  - 句式：长句偏好/短句偏好/混合
  - 用词：书面/通俗/专业术语密度
  - 结构：段落长度/转折词/列表偏好
  - 特殊习惯：口头禅/常用表达/标点习惯
  ↓
输出：风格画像（结构化 JSON）
```

### 阶段 2：保存风格画像

将风格画像保存为本地文件，供后续写作时参考。

```bash
# 风格画像存储路径
~/.xiaodazi/styles/

# 文件格式
~/.xiaodazi/styles/{用户名}_default.json
~/.xiaodazi/styles/{用户名}_{场景名}.json  # 可按场景保存多套风格
```

**风格画像结构**：

```json
{
  "name": "默认风格",
  "created_at": "2025-01-15",
  "updated_at": "2025-02-07",
  "sample_count": 3,
  "profile": {
    "tone": "半正式，亲切但不随意",
    "sentence_style": "短句为主，偶尔用长句做总结",
    "vocabulary": "通俗用词，避免学术术语，喜欢用比喻",
    "structure": "开头直入主题，段落短（3-5句），善用列表",
    "special_habits": [
      "喜欢用破折号做补充说明",
      "段尾常用反问句引发思考",
      "数字用阿拉伯数字不用中文"
    ]
  },
  "few_shot_examples": [
    {
      "context": "写产品介绍",
      "sample": "（截取的 200 字典型片段）"
    }
  ]
}
```

### 阶段 3：应用风格

写作任务时，读取风格画像并注入到提示词：

```
用户请求：「帮我写一篇关于 AI 的文章」
  ↓
读取风格画像 → 提取关键约束
  ↓
生成时遵循：
  - 语气：半正式，亲切
  - 句式：短句为主
  - 用词：通俗，多用比喻
  - 结构：开头直入主题，段落 3-5 句
  ↓
输出：符合用户风格的文章
```

### 阶段 4：持续学习

每次用户修改输出或给出反馈时，更新风格画像：

- 用户说「太正式了」→ 调整 tone 为更口语
- 用户手动修改了输出 → 对比差异，更新偏好
- 积累 5+ 次反馈后自动更新画像

## 命令参考

### 保存风格画像

```bash
mkdir -p ~/.xiaodazi/styles
cat > ~/.xiaodazi/styles/default.json << 'EOF'
{
  "name": "默认风格",
  ...
}
EOF
```

### 读取风格画像

```bash
cat ~/.xiaodazi/styles/default.json
```

### 列出已有风格

```bash
ls ~/.xiaodazi/styles/
```

## 输出规范

- 分析风格时，用通俗语言描述（不用语言学术语）
- 保存成功后告知用户「已记住你的写作风格」
- 写作时不提及「我在使用你的风格画像」，自然地写
- 用户可以说「换个正式的风格」临时切换，不影响保存的画像
