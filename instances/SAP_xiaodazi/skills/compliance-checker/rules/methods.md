# 方法适当性规则（6 条）
METHOD-01 [CRITICAL]: 统计方法与数据类型匹配（count_rate→NB, continuous→MMRM, time_to_event→Cox, binary→Logistic）
METHOD-02 [MAJOR]: 模型协变量与 Protocol 一致
METHOD-03 [MAJOR]: MMRM 必须指定协方差结构和自由度方法
METHOD-04 [MAJOR]: 负二项回归必须指定分布和链接函数
METHOD-05 [MINOR]: 敏感性分析应说明目的
METHOD-06 [MAJOR]: 多重比较检验顺序完整
