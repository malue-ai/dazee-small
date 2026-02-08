---
name: quiz-maker
description: Create quizzes with multiple question types including multiple choice, true/false, fill-in-the-blank, and matching. Supports difficulty levels and answer explanations.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 测验出题

根据学习材料或主题，自动生成多种题型的测验，帮助用户巩固知识。

## 使用场景

- 用户说「帮我出几道题」「根据这个材料出测验」「帮我复习 XX」
- 学生复习备考，需要练习题
- 教育工作者制作教学测验
- 配合 `skill-tutor` 做间隔重复复习

## 执行方式

直接使用 LLM 能力生成题目，无需额外工具。

### 支持的题型

#### 1. 选择题（单选/多选）

```markdown
**Q1.** 以下哪个是 Python 中的不可变数据类型？
- A. list
- B. dict
- C. tuple ✅
- D. set

> 💡 解析：tuple（元组）创建后不能修改，是不可变类型。
```

#### 2. 判断题

```markdown
**Q2.** 判断：HTTP 是有状态协议。
- ❌ 错误

> 💡 解析：HTTP 是无状态协议，每次请求独立，不保留之前请求的信息。
```

#### 3. 填空题

```markdown
**Q3.** TCP 建立连接需要 ______ 次握手。
- 答案：三

> 💡 解析：TCP 三次握手：SYN → SYN-ACK → ACK。
```

#### 4. 简答题

```markdown
**Q4.** 简述什么是数据库索引，以及它的优缺点。
> 参考要点：加速查询、增加写入开销、占用额外存储空间
```

### 出题策略

- **难度梯度**：从易到难，先基础后综合
- **覆盖均匀**：确保涵盖材料的各个章节/知识点
- **干扰项质量**：选择题的错误选项要有迷惑性，不能一眼看出
- **解析详细**：每道题附带解析，错了也能学到

### 互动模式

支持两种模式：

1. **一次性出题**：生成完整试卷
2. **逐题模式**：一次出一道，用户作答后给反馈，再出下一道

## 输出规范

- 默认附带答案和解析
- 如果用户要练习，先隐藏答案（用折叠格式）
- 统计对错比例，指出薄弱知识点
- 题目数量按用户要求，默认 10 道
