---
name: slidespeak-slide-editor
description: Edit slides in existing SlideSpeak presentations - insert, regenerate, or remove slides using AI
priority: high
---

# SlideSpeak Slide Editor

在 SlideSpeak 系统中编辑已生成的 PPT，支持智能添加、重新生成或删除幻灯片。

**API 文档**: [https://docs.slidespeak.co/basics/api-references/edit-slide/](https://docs.slidespeak.co/basics/api-references/edit-slide/)

## API 规范摘要

### 端点

```
POST https://api.slidespeak.co/api/v1/presentation/edit/slide
```

### 三种编辑操作

| 操作 | 说明 | 消耗 Credits | Prompt 必需 |
|------|------|-------------|------------|
| **INSERT** | 在指定位置插入新幻灯片 | ✅ 1 credit | ✅ 是 |
| **REGENERATE** | 重新生成已有幻灯片 | ✅ 1 credit | ✅ 是 |
| **REMOVE** | 删除指定位置的幻灯片 | ❌ 0 credit | ❌ 否 |

### 必需参数

1. **presentation_id** (string): PPT 的 ID（从生成时获得）
2. **edit_type** (enum): `INSERT` | `REGENERATE` | `REMOVE`
3. **position** (number): 幻灯片位置索引（从 0 开始）
4. **prompt** (string): 内容描述（INSERT/REGENERATE 必需）

### 可选参数

- `document_uuids`: 参考文档的 UUID 列表
- `fetch_images`: 是否包含图片（继承自 PPT 设置）
- `verbosity`: `concise` | `standard` | `text-heavy`
- `tone`: `default` | `casual` | `professional` | `funny` | `educational` | `sales_pitch`
- `add_speaker_notes`: 是否添加演讲者备注
- `use_general_knowledge`: 是否使用通用知识扩展
- `use_wording_from_document`: 是否使用文档原文
- `use_document_images`: 是否使用文档中的图片

### 异步处理

```
1. 发送编辑请求 → 返回 task_id
2. 轮询 /task_status/{task_id} 直到 status = "SUCCESS"
3. 使用 task_result 中的 url 下载编辑后的 PPT
```

## 使用场景

### 1. 在对话中持续完善 PPT

```
用户: "帮我生成一个产品介绍 PPT"
Agent: [生成 PPT，保存 presentation_id]

用户: "在第3页后添加一页关于定价方案的内容"
Agent: [使用 slidespeak_edit_slide]
      → INSERT at position=3
      → prompt="添加定价方案页，包含三个套餐"

用户: "把第5页重新生成，要更详细一些"
Agent: [使用 slidespeak_edit_slide]
      → REGENERATE at position=4
      → prompt="重新生成，添加更多技术细节"

用户: "删除第7页"
Agent: [使用 slidespeak_edit_slide]
      → REMOVE at position=6
```

### 2. 快速迭代优化

```
用户: "这个 PPT 的市场分析页面太简单了，帮我扩展成两页"
Agent: 
  1. REGENERATE 原页面（更详细）
  2. INSERT 新页面（添加补充内容）
```

### 3. 动态调整结构

```
用户: "把所有关于竞争对手的内容集中到一起"
Agent:
  1. INSERT 新的"竞争分析"页
  2. 整合现有相关内容
  3. REMOVE 旧的分散页面
```

## 使用流程

### 自动流程（推荐）

系统会自动从对话历史中提取 `presentation_id`：

```
# 第一步：生成 PPT
用户: "生成一个关于 AI 的 PPT"
Agent: [slidespeak-generator] → presentation_id = "xxx"
       [自动保存到对话上下文]

# 第二步：编辑 PPT（自动识别）
用户: "在第2页后添加一页关于机器学习的内容"
Agent: [自动提取 presentation_id]
       [理解意图：INSERT at position=2]
       [调用 slidespeak_edit_slide]
```

### 手动指定（高级用法）

如果需要编辑之前的 PPT：

```
用户: "编辑 presentation_id 为 cmgt32cut0000h3ovex8dbzmn 的 PPT，
      在第5页后添加总结页"
Agent: [使用指定的 presentation_id]
```

## 意图识别规则

### INSERT（插入）关键词

- "添加一页..."
- "插入一个幻灯片..."
- "在第 X 页后增加..."
- "新增一页..."
- "补充一页..."

**示例**：
```
用户: "在第3页后添加一页关于团队介绍的内容"
→ edit_type: INSERT
→ position: 3
→ prompt: "添加团队介绍页，包含核心成员和角色"
```

### REGENERATE（重新生成）关键词

- "重新生成第 X 页..."
- "把第 X 页改成..."
- "优化第 X 页..."
- "第 X 页要更详细..."
- "调整第 X 页的内容..."

**示例**：
```
用户: "把第5页重新生成，要包含图表"
→ edit_type: REGENERATE
→ position: 4 (索引从0开始)
→ prompt: "重新生成，使用图表布局展示数据"
```

### REMOVE（删除）关键词

- "删除第 X 页"
- "去掉第 X 页"
- "移除第 X 页"
- "不要第 X 页了"

**示例**：
```
用户: "删除第7页"
→ edit_type: REMOVE
→ position: 6
→ prompt: null
```

## 位置索引说明

⚠️ **重要**：SlideSpeak 使用绝对索引（从 0 开始）

```
幻灯片结构：
[0] 封面（Cover）              ← 不能编辑
[1] 目录（Table of Contents）   ← 不能编辑
[2] 第一页内容                  ← 可以编辑
[3] 第二页内容                  ← 可以编辑
[4] 第三页内容                  ← 可以编辑
...
```

**用户说"第3页"，实际索引是多少？**

取决于 PPT 是否有封面和目录：

| 用户说的 | 有封面+目录 | 只有封面 | 无封面 |
|---------|-----------|---------|-------|
| 第1页内容 | position=2 | position=1 | position=0 |
| 第2页内容 | position=3 | position=2 | position=1 |
| 第3页内容 | position=4 | position=3 | position=2 |

**推荐策略**：
1. 询问用户：封面算不算第1页？
2. 根据生成时的配置自动计算偏移量
3. 提供友好的错误提示

## Prompt 编写原则

### 好的 Prompt

```python
# ✅ 清晰、具体、可执行
"添加一页关于产品定价的幻灯片，包含三个套餐（基础版、专业版、企业版），
 每个套餐列出价格、核心功能和适用场景。使用对比布局。"

# ✅ 指定布局和风格
"重新生成这一页，使用 CHART 布局展示季度销售数据，
 包含柱状图和增长趋势线。采用专业商务风格。"

# ✅ 明确内容要求
"插入一页团队介绍，包含5位核心成员的姓名、职位、
 主要职责和代表性成就。使用 ITEMS 布局。"
```

### 不好的 Prompt

```python
# ❌ 太模糊
"添加一页内容"
→ AI 不知道要生成什么

# ❌ 太长太复杂
"添加一页关于市场分析的内容，要包括市场规模、增长趋势、
 竞争格局、用户画像、痛点分析、解决方案、商业模式、
 竞争优势、风险分析、未来展望..."
→ 一页放不下，应该拆分成多页

# ❌ 缺少上下文
"把这一页改一下"
→ 改成什么样？
```

## 工具调用格式

### 基本用法

```python
slidespeak_edit_slide(
    presentation_id="cmgt32cut0000h3ovex8dbzmn",
    edit_type="INSERT",
    position=3,
    prompt="添加一页关于市场分析的内容，包含市场规模、增长趋势、竞争格局三个要点",
    fetch_images=True,
    tone="professional",
    verbosity="standard"
)
```

### 插入新幻灯片

```python
slidespeak_edit_slide(
    presentation_id="cmgt32cut0000h3ovex8dbzmn",
    edit_type="INSERT",
    position=2,  # 在第2页后插入
    prompt="添加产品特性页，列出5个核心功能：AI驱动、实时协作、云端存储、跨平台、安全加密",
    fetch_images=True,
    verbosity="standard",
    tone="professional"
)
```

### 重新生成幻灯片

```python
slidespeak_edit_slide(
    presentation_id="cmgt32cut0000h3ovex8dbzmn",
    edit_type="REGENERATE",
    position=4,  # 重新生成第5页
    prompt="重新生成这一页，使用 COMPARISON 布局对比传统方案和我们的方案，突出我们的优势",
    verbosity="text-heavy"  # 更详细
)
```

### 删除幻灯片

```python
slidespeak_edit_slide(
    presentation_id="cmgt32cut0000h3ovex8dbzmn",
    edit_type="REMOVE",
    position=6,  # 删除第7页
    prompt=None  # REMOVE 不需要 prompt
)
```

### 使用文档内容

```python
# 先上传文档，获得 document_uuid
# 然后在编辑时引用
slidespeak_edit_slide(
    presentation_id="cmgt32cut0000h3ovex8dbzmn",
    edit_type="INSERT",
    position=5,
    prompt="根据上传的市场报告，添加一页总结市场趋势",
    document_uuids=["b12f2c9c-1a2b-4d3e-9f4a-5b6c7d8e9f01"],
    use_wording_from_document=True,
    use_document_images=True
)
```

## 异步处理机制

Edit Slide API 是异步的，需要轮询任务状态：

```python
# 1. 发送编辑请求
response = slidespeak_edit_slide(...)
task_id = response["task_id"]

# 2. 轮询任务状态（由工具自动处理）
while True:
    status = check_task_status(task_id)
    
    if status == "SUCCESS":
        # 任务完成
        download_url = get_download_url(task_id)
        break
    elif status == "FAILED":
        # 任务失败
        raise Exception("Edit failed")
    else:
        # 继续等待
        await sleep(2)  # 每2秒检查一次
```

**用户体验优化**：
```
用户: "在第3页后添加一页"
Agent: 
  → "正在添加幻灯片... 🔄"
  → [轮询中]
  → "添加成功！已更新 PPT ✅"
  → [提供下载链接]
```

## 错误处理

### 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| `presentation_id not found` | ID 不存在 | 检查 ID 是否正确 |
| `Invalid position` | 位置超出范围 | 使用有效的索引 |
| `Cannot edit cover/TOC` | 尝试编辑封面/目录 | 只编辑内容页 |
| `Prompt required for INSERT` | INSERT 缺少 prompt | 提供内容描述 |
| `Task timeout` | 任务超时 | 检查网络，重试 |

### 容错策略

```python
# 建议：增加重试机制
max_retries = 3
for attempt in range(max_retries):
    try:
        result = slidespeak_edit_slide(...)
        if result["success"]:
            break
    except Exception as e:
        if attempt == max_retries - 1:
            raise
        print(f"重试 {attempt + 1}/{max_retries}...")
        await sleep(5)
```

## 最佳实践

### 1. 维护对话状态

```python
# 在生成 PPT 时保存 presentation_id
class ConversationState:
    def __init__(self):
        self.current_presentation_id = None
        self.presentation_metadata = {}
    
    def save_presentation(self, pres_id, metadata):
        self.current_presentation_id = pres_id
        self.presentation_metadata[pres_id] = metadata
```

### 2. 智能索引计算

```python
def calculate_position(user_page_number, has_cover, has_toc):
    """
    计算实际的 position 索引
    
    Args:
        user_page_number: 用户说的页码（1-based）
        has_cover: 是否有封面
        has_toc: 是否有目录
    
    Returns:
        实际的 position 索引（0-based）
    """
    offset = 0
    if has_cover:
        offset += 1
    if has_toc:
        offset += 1
    
    return user_page_number - 1 + offset
```

### 3. 批量操作

```python
# 场景：一次性进行多个编辑
edits = [
    {"type": "INSERT", "position": 3, "prompt": "..."},
    {"type": "REGENERATE", "position": 5, "prompt": "..."},
    {"type": "REMOVE", "position": 8}
]

for edit in edits:
    result = slidespeak_edit_slide(
        presentation_id=pres_id,
        edit_type=edit["type"],
        position=edit["position"],
        prompt=edit.get("prompt")
    )
    # 等待每个操作完成
    wait_for_completion(result["task_id"])
```

### 4. 用户确认机制

```python
# 对于重要操作，先确认
用户: "删除第5页"
Agent: "确认要删除第5页（市场分析）吗？这个操作不可撤销。"
用户: "确认"
Agent: [执行删除]
```

## 与其他 Skills 的协作

### 与 slidespeak-generator 配合

```
1. slidespeak-generator: 生成初始 PPT
   → 返回 presentation_id
   
2. slidespeak-slide-editor: 迭代完善
   → INSERT: 添加缺失内容
   → REGENERATE: 优化现有页面
   → REMOVE: 删除多余页面
   
3. slidespeak-editor: 批量个性化
   → 替换客户名称、数据等
```

### 典型工作流

```
用户: "生成一个产品 PPT"
  ↓ slidespeak-generator
  [生成基础 PPT，10页]
  
用户: "添加一页定价方案"
  ↓ slidespeak-slide-editor (INSERT)
  [在合适位置插入定价页]
  
用户: "第3页太简单了，重新生成详细一点"
  ↓ slidespeak-slide-editor (REGENERATE)
  [重新生成第3页]
  
用户: "把公司名称都改成'ABC科技'"
  ↓ slidespeak-editor
  [批量替换所有页面的公司名]
```

## 成功标准

✅ **功能正确性**：
- 正确识别编辑意图（INSERT/REGENERATE/REMOVE）
- 准确计算 position 索引
- 成功处理异步任务

✅ **内容质量**：
- Prompt 清晰明确
- 生成内容符合要求
- 布局选择合理

✅ **用户体验**：
- 快速响应（合理的等待时间）
- 友好的进度提示
- 清晰的错误信息

## 故障排查

### 问题 1: presentation_id 找不到

```
现象: "Presentation not found"

可能原因:
1. PPT 刚生成，ID 还未保存
2. 对话历史被清空
3. ID 输入错误

解决方案:
1. 检查对话历史中的 ID
2. 让用户提供下载链接中的 ID
3. 重新生成 PPT
```

### 问题 2: 任务一直 PENDING

```
现象: 轮询超时

可能原因:
1. 服务器负载高
2. Prompt 太复杂
3. 网络问题

解决方案:
1. 延长超时时间
2. 简化 Prompt
3. 检查网络连接
4. 联系 SlideSpeak 支持
```

### 问题 3: 索引错误

```
现象: "Invalid position"

可能原因:
1. position 超出范围
2. 封面/目录偏移量计算错误

解决方案:
1. 检查 PPT 总页数
2. 确认是否有封面和目录
3. 使用正确的索引计算
```

## 参考资源

- **官方 API 文档**: [SlideSpeak Edit Slide](https://docs.slidespeak.co/basics/api-references/edit-slide/)
- **异步任务处理**: [Get Task Status](https://docs.slidespeak.co/basics/api-references/get-task-status/)
- **下载 PPT**: [Download Presentation](https://docs.slidespeak.co/basics/api-references/download-presentation/)
- **架构文档**: [00-ARCHITECTURE-OVERVIEW.md](../../../docs/00-ARCHITECTURE-OVERVIEW.md)

