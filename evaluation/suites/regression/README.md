# 回归测试套件

从生产失败案例自动生成的回归测试套件。

## 生成方式

使用 `evaluation/case_converter.py` 将失败案例转换为评测任务：

```python
from evaluation.case_converter import CaseConverter
from core.monitoring.failure_detector import FailureDetector

detector = FailureDetector()
converter = CaseConverter(output_dir="evaluation/suites/regression")

# 获取已审核的失败案例
cases = detector.get_cases(status="reviewed", limit=50)

# 转换并导出
tasks = converter.convert_cases(cases)
converter.export_to_yaml(tasks, suite_name="regression_from_failures")
```

## 更新频率

- 每周自动生成一次
- 从最近 7 天的失败案例中提取
- 只包含已审核且提供参考答案的案例

## 文件命名

- `regression_YYYYMMDD_HHMMSS.yaml` - 自动生成的套件文件
