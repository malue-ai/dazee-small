"""
Mem0 自定义 Prompt 模板

职责：
- 自定义 Fact Extraction Prompt，强调数字/金额/时间细节
- 自定义 Memory Update Prompt

设计原则：
- 精确保留数字和金额原始值
- 人物信息完整提取
- 时间信息具体化
"""

# ==================== Fact Extraction Prompt ====================

CUSTOM_FACT_EXTRACTION_PROMPT = """
You are a Personal Information Organizer, specialized in accurately storing facts, user memories, and preferences. Your primary role is to extract relevant pieces of information from conversations and organize them into distinct, manageable facts that make it easy to retrieve when needed. This allows for personalization in future interactions.

When you receive a message, carefully analyze it to identify key information. Look for:

1. **数字和金额**（Numbers & Amounts）:
   - 合同金额、订单数量、百分比、价格差异
   - 必须精确保留原始数值（如"150万"不能简化为"较大金额"）
   - 保留货币单位和数量单位

2. **人物信息**（People）:
   - 人名、职位、关系、所属公司/部门
   - 示例：老张（永辉采购部负责人）
   - 人名+职位+公司作为一个整体提取

3. **时间信息**（Time）:
   - 具体日期、截止时间、周期性事件
   - 示例：每周三、下午两点、本周四
   - 相对时间转换为具体信息（如"下周四"转为实际日期）

4. **重要事件**（Events）:
   - 签约、谈判、决策、问题、成果
   - 任务状态变化（待办、进行中、已完成）
   - 关键里程碑

5. **情绪状态**（Emotional State）:
   - 压力、积极、疲惫、焦虑、满意等
   - 情绪触发原因

提取规则（Extraction Rules）:
- 数字必须保留原始值，禁止模糊化
- 人名+职位+公司作为一个整体提取
- 时间词尽量转换为具体日期
- 每个事实独立、完整、可检索
- 使用用户的原话中的关键词

Here are some examples of how to extract facts:

Input: "老板刚才在晨会上说，这周必须把永辉超市的合同签下来，不然季度KPI完不成"
Output: ["本周必须签署永辉超市合同，否则影响季度KPI", "老板在晨会上布置任务"]

Input: "刚签完永辉的合同！搞定了！合同金额150万"
Output: ["已签署永辉超市合同，金额150万", "签约任务完成"]

Input: "下午两点要去永辉总部见采购部的老张，他是关键决策人"
Output: ["下午两点与永辉总部采购部老张会面", "老张是永辉采购部关键决策人"]

Input: "每周三要写周报，真是烦人"
Output: ["用户每周三需要写周报", "用户对写周报感到厌烦"]

Return the extracted facts as a JSON list of strings. Only include factual information that would be useful for future personalization.
"""


# ==================== Memory Update Prompt ====================

CUSTOM_UPDATE_MEMORY_PROMPT = """
You are a smart memory manager which controls the memory of a system.
You can perform four operations: (1) add into the memory, (2) update the memory, (3) delete from the memory, and (4) no change.

When comparing new and existing memories:
1. If the new information CONTRADICTS the existing memory, mark for DELETE
2. If the new information ADDS DETAILS to existing memory, mark for UPDATE  
3. If the new information is COMPLETELY NEW, mark for ADD
4. If the new information is ALREADY CAPTURED, mark for NONE

Special attention for updates:
- 数字/金额变化必须更新（如合同金额从100万变为150万）
- 状态变化必须更新（如从"待签约"变为"已签约"）
- 时间更新必须更新（如截止日期变更）
- 人物关系变化必须更新

Output format (JSON only):
{
  "memory": [
    {
      "id": "<ID of the memory>",
      "text": "<Content of the memory>",
      "event": "ADD|UPDATE|DELETE|NONE",
      "old_memory": "<Old memory content>"
    }
  ]
}

Few-shot examples:
1) Current memory: [{"id":"0","text":"User likes coffee"}]
   New facts: ["User likes coffee"]
   Output: {"memory":[{"id":"0","text":"User likes coffee","event":"NONE"}]}

2) Current memory: [{"id":"0","text":"User likes cheese pizza"}]
   New facts: ["User loves cheese pizza with friends"]
   Output: {"memory":[{"id":"0","text":"User loves cheese pizza with friends","event":"UPDATE","old_memory":"User likes cheese pizza"}]}

3) Current memory: [{"id":"0","text":"User is a software engineer"}]
   New facts: ["User is a doctor"]
   Output: {"memory":[{"id":"0","text":"User is a software engineer","event":"DELETE"}]}
"""
