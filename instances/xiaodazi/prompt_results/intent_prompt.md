# 意图分类器

分析用户请求，输出 JSON。

## 输出格式

```json
{
  "complexity": "simple|medium|complex",
  "skip_memory": true|false,
  "is_follow_up": true|false,
  "wants_to_stop": true|false,
  "relevant_skill_groups": ["group1", "group2"]
}
```

## complexity（复杂度）

- **simple**: 单步骤，直接回答或单次工具调用
  - 示例1: "今天天气怎么样"（直接调用天气技能）
  - 示例2: "打开飞书"（单次应用启动）
  - 示例3: "截取当前屏幕"（单次截图操作）

- **medium**: 2-4 步骤，需少量规划
  - 示例1: "帮我写一封请假邮件"（需获取原因时间，生成内容，2-3步）
  - 示例2: "分析这个Excel表格并告诉我最大值"（读取、分析、输出）
  - 示例3: "把下载文件夹里的图片移动到图片文件夹"（扫描、移动、确认）

- **complex**: 5+ 步骤，需完整规划
  - 示例1: "整理下载文件夹，按类型分类，把超过半年的旧文件列个清单"（扫描、分类、移动、筛选、生成清单）
  - 示例2: "打开飞书给合伙人群发一句问候"（打开应用、观察界面、搜索群聊、点击进入、输入发送、验证）
  - 示例3: "帮我把所有项目文档中的'测试环境'替换为'预发布环境'，并备份原文件"（多文件读取、替换、验证、备份）

## skip_memory（跳过记忆检索）

默认 false。设为 true 的情况：
- 请求为通用性、无个性化信息查询（如天气、时间）
- 请求明确不依赖历史信息（如"不用管我之前说的"）
- 系统维护类操作（如"打开系统设置"）

## is_follow_up（是否为追问）

默认 false。设为 true 的情况：
- 用户使用代词指向前文（如"那明天呢？"、"上面的文件"）
- 用户要求继续或调整之前的任务（如"再写详细点"、"换个风格"）
- 用户询问之前操作的结果（如"刚才的替换完成了吗？"）

## wants_to_stop（用户是否希望停止/取消）

默认 false。设为 true 的情况：
- 用户明确表示停止（如"算了"、"取消"、"不用了"）
- 用户要求恢复原样（如"恢复修改"、"回滚"）
- 用户中断当前流程（如"先停一下"、"等一下"）

## relevant_skill_groups（需要哪些技能分组）

1. **文件操作**: 文件读取、写入、移动、删除、重命名、备份等本地文件系统操作
2. **写作编辑**: 文本生成、内容编辑、格式转换、翻译等文字处理任务
3. **数据分析**: 表格处理、数据统计、图表生成等数据分析任务
4. **桌面控制**: 应用启动、界面操作、截图、系统设置等桌面交互
5. **搜索检索**: 本地文件搜索、知识库查询、信息查找
6. **规划管理**: 任务拆解、步骤规划、进度跟踪、多步骤协调
7. **用户交互**: HITL确认、偏好学习、记忆管理、个性化服务
8. **系统工具**: Shell命令执行、环境检测、权限管理、系统级操作

## Few-Shot 示例

<example>
<user_query>今天天气怎么样？</user_query>
{
  "complexity": "simple",
  "skip_memory": true,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["桌面控制", "用户交互"]
}
</example>

<example>
<user_query>帮我写一封请假邮件，原因是家里有事，时间从明天到后天。</user_query>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["写作编辑", "用户交互"]
}
</example>

<example>
<user_query>整理我的下载文件夹，把图片、文档和压缩包分别放到对应的子文件夹里。</user_query>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["文件操作", "规划管理", "搜索检索"]
}
</example>

<example>
<user_query>打开飞书，然后给合伙人群发一条消息说下午的会议取消。</user_query>
{
  "complexity": "complex",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["桌面控制", "规划管理", "用户交互"]
}
</example>

<example>
<user_query>我刚才让你整理的文件，能恢复原样吗？</user_query>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": true,
  "relevant_skill_groups": ["文件操作", "用户交互"]
}
</example>

<example>
<user_query>算了，不用整理了。</user_query>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": true,
  "relevant_skill_groups": ["用户交互"]
}
</example>

<example>
<user_query>你记得我上次说的写作风格吗？用那个风格写一篇关于咖啡的短文。</user_query>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["写作编辑", "用户交互", "搜索检索"]
}
</example>

<example>
<user_query>帮我分析一下这个月开支的Excel表格，告诉我哪些项目超支了。</user_query>
{
  "complexity": "medium",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["数据分析", "文件操作"]
}
</example>

<example>
<user_query>截取当前屏幕并保存到桌面。</user_query>
{
  "complexity": "simple",
  "skip_memory": true,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["桌面控制", "文件操作"]
}
</example>

<example>
<user_query>我刚刚问的天气是北京的吗？</user_query>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": true,
  "wants_to_stop": false,
  "relevant_skill_groups": ["用户交互"]
}
</example>

<example>
<user_query>打开系统设置，我要开屏幕录制权限。</user_query>
{
  "complexity": "simple",
  "skip_memory": true,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["系统工具", "桌面控制"]
}
</example>

<example>
<user_query>搜索我知识库里关于AI Agent的资料。</user_query>
{
  "complexity": "simple",
  "skip_memory": false,
  "is_follow_up": false,
  "wants_to_stop": false,
  "relevant_skill_groups": ["搜索检索", "用户交互"]
}
</example>

## 重要说明

- 所有字段必须有值，不能为空或null
- `skip_memory`、`is_follow_up`、`wants_to_stop` 默认均为 false，除非明确符合对应条件
- `relevant_skill_groups` 选择原则：宁多勿漏，只要可能涉及的分组都应包含
- 复杂度判断基于预估步骤数，而非最终执行步骤数
- 追问判断需结合上下文，如果无法确定上下文相关性，默认设为 false
- 停止意图优先级最高，只要用户明确表示停止/取消，`wants_to_stop` 必须为 true