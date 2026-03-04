---
name: cloud-agent
description: 将任务委托给云端 Agent 执行。云端拥有联网搜索、代码沙箱、项目发布等本地不具备的能力，适用于持续运行、沙箱执行、深度调研三类场景。支持带文件委托。
metadata:
  xiaodazi:
    dependency_level: cloud_api
    os: [common]
    backend_type: tool
    user_facing: true
---

# 云端 Agent 委托

云端 Agent 是本地的能力扩展。本地优先处理，但当本地不适合或无法完成时，委托云端。

## 云端具备的能力（本地没有或较弱）

- **联网搜索**：Tavily、Exa 深度搜索，多来源信息聚合
- **网页爬取**：Crawl4AI、Puppeteer 全页面爬取与数据提取
- **代码沙箱**：Docker 隔离环境，安全执行任意代码
- **项目构建与发布**：沙箱内 build + 发布到公网 URL
- **文件处理**：支持接收 PDF / Excel / 图片等附件并分析

## 什么时候委托云端

满足以下**任一理由**即可委托：

### 理由 1：持续运行 — 任务可能比本次开机时长更久

<example>
<query>每天早上 8 点帮我看科技新闻</query>
<use_cloud>true</use_cloud>
<reason>定时任务，8 点用户可能没开机</reason>
</example>

<example>
<query>周末帮我盯一下 XX 商品有没有降价</query>
<use_cloud>true</use_cloud>
<reason>跨天监控，周末不一定开电脑</reason>
</example>

<example>
<query>花一下午深度调研这个行业，不着急</query>
<use_cloud>true</use_cloud>
<reason>多小时任务，用户可能中途关机</reason>
</example>

<example>
<query>下午 3 点提醒我开会</query>
<use_cloud>false</use_cloud>
<reason>用户正在用电脑，本地提醒更即时可靠</reason>
</example>

### 理由 2：沙箱执行 — 需要运行代码、构建项目、发布应用

<example>
<query>帮我跑一下这段 Python 数据分析脚本</query>
<use_cloud>true</use_cloud>
<reason>需要隔离沙箱环境安全执行代码</reason>
</example>

<example>
<query>做一个生日邀请网页，发链接给朋友</query>
<use_cloud>true</use_cloud>
<reason>沙箱构建项目 + 发布到公网 URL</reason>
</example>

<example>
<query>构建一个贪食蛇网页小游戏</query>
<use_cloud>true</use_cloud>
<reason>需要沙箱构建、运行 dev server、可发布</reason>
</example>

<example>
<query>帮我做个 PPT</query>
<use_cloud>false</use_cloud>
<reason>本地有 PPT Skill，无需沙箱</reason>
</example>

### 理由 3：深度调研 — 需要联网搜索多来源信息

<example>
<query>调研最新的 AI Agent 框架并写对比报告</query>
<use_cloud>true</use_cloud>
<reason>需要多来源联网搜索（Tavily/Exa）+ 长时间分析</reason>
</example>

<example>
<query>帮我分析这三家竞品的功能差异，写一份对比分析</query>
<use_cloud>true</use_cloud>
<reason>需要爬取多个竞品网站 + 深度对比</reason>
</example>

<example>
<query>搜一下明天上海天气</query>
<use_cloud>false</use_cloud>
<reason>简单搜索，本地搜索工具秒级返回</reason>
</example>

<example>
<query>搜一下最新的 AI 论文</query>
<use_cloud>false</use_cloud>
<reason>单次搜索，本地有 arXiv/论文搜索 Skill，即时返回</reason>
</example>

### 绝对不要委托云端的场景

<example>
<query>帮我整理桌面上的文件</query>
<use_cloud>false</use_cloud>
<reason>纯本地文件操作，云端无法访问本地桌面</reason>
</example>

<example>
<query>打开微信</query>
<use_cloud>false</use_cloud>
<reason>本地应用操作，云端无法控制桌面应用</reason>
</example>

<example>
<query>帮我写一封邮件</query>
<use_cloud>false</use_cloud>
<reason>文本生成是本地基础能力，无需委托</reason>
</example>

## 使用方式

基本调用：

```
cloud_agent(task="调研 AI Agent 赛道最新动态并写一份分析报告")
```

带上下文：

```
cloud_agent(
    task="基于以下竞品列表做深度调研",
    context="竞品: Manus, Devin, Bolt..."
)
```

带文件（PDF / Excel / 图片等）：

```
cloud_agent(
    task="分析这份行业报告并提取关键数据",
    files=[{"file_url": "/path/to/report.pdf", "file_name": "行业报告.pdf", "file_type": "application/pdf"}]
)
```

本地文件会自动上传到云端后再传给云端 Agent 处理。

## 执行特性

- **流式输出**：云端默认流式返回，执行过程中会实时推送进度（思考中 → 工具调用 → 生成文本）
- **执行时间**：简单任务 10-30 秒，深度调研 1-3 分钟，沙箱构建项目 2-5 分钟
- **文件支持**：可传入 PDF、Excel、CSV、图片等文件，本地文件会自动上传到云端 S3
- **网络依赖**：需要网络连接，不可达时工具会返回明确错误提示
- **结果格式**：返回纯文本结果，如需生成本地文件（PPT / Excel），应在本地完成

