"""
评估告警机制
在评估指标异常时发送告警通知
"""
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from .metrics import MetricSummary, MetricResult


class AlertSeverity(str, Enum):
    """告警严重程度"""
    CRITICAL = "critical"  # 严重：阻塞发布
    WARNING = "warning"   # 警告：建议修复
    INFO = "info"         # 信息：提示关注


@dataclass
class Alert:
    """告警"""
    severity: AlertSeverity
    title: str
    message: str
    metric_name: Optional[str] = None
    current_value: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


class AlertRule:
    """告警规则"""
    
    def __init__(
        self,
        name: str,
        condition: Callable[[MetricSummary], bool],
        severity: AlertSeverity,
        title: str,
        message_template: str
    ):
        """
        初始化告警规则
        
        Args:
            name: 规则名称
            condition: 条件函数，返回 True 时触发告警
            severity: 告警严重程度
            title: 告警标题
            message_template: 告警消息模板
        """
        self.name = name
        self.condition = condition
        self.severity = severity
        self.title = title
        self.message_template = message_template
    
    def check(self, summary: MetricSummary) -> Optional[Alert]:
        """
        检查是否满足告警条件
        
        Args:
            summary: 指标汇总
            
        Returns:
            如果满足条件，返回告警对象；否则返回 None
        """
        if self.condition(summary):
            return Alert(
                severity=self.severity,
                title=self.title,
                message=self.message_template.format(
                    overall_score=summary.overall_score,
                    quality_tier=summary.quality_tier
                )
            )
        return None


class AlertManager:
    """告警管理器"""
    
    def __init__(self):
        """初始化告警管理器"""
        self.rules: List[AlertRule] = []
        self.notifiers: List[Callable[[List[Alert]], None]] = []
        
        # 注册默认告警规则
        self._register_default_rules()
    
    def _register_default_rules(self):
        """注册默认告警规则"""
        
        # 1. 回归检测
        self.add_rule(AlertRule(
            name="regression_detected",
            condition=lambda s: s.regression_detected,
            severity=AlertSeverity.CRITICAL,
            title="性能回归检测",
            message="检测到性能回归，总体得分相比基线显著下降。建议立即检查最新变更并暂停发布。"
        ))
        
        # 2. 质量分层 - POOR
        self.add_rule(AlertRule(
            name="quality_tier_poor",
            condition=lambda s: s.quality_tier == "POOR",
            severity=AlertSeverity.CRITICAL,
            title="质量分层：POOR",
            message="质量分层为 POOR（总分 {overall_score:.1%}），低于可接受标准。建议暂停发布，进行全面检查。"
        ))
        
        # 3. 质量分层 - ACCEPTABLE
        self.add_rule(AlertRule(
            name="quality_tier_acceptable",
            condition=lambda s: s.quality_tier == "ACCEPTABLE",
            severity=AlertSeverity.WARNING,
            title="质量分层：ACCEPTABLE",
            message="质量分层为 ACCEPTABLE（总分 {overall_score:.1%}），接近阈值下限。建议优化后再发布。"
        ))
        
        # 4. 任务成功率过低
        self.add_rule(AlertRule(
            name="task_success_rate_low",
            condition=lambda s: self._get_metric_value(s, "task_success_rate") < 0.70,
            severity=AlertSeverity.CRITICAL,
            title="任务成功率过低",
            message="任务成功率低于 70%，大量任务执行失败。建议检查 Agent 核心逻辑。"
        ))
        
        # 5. 代码级检查通过率低
        self.add_rule(AlertRule(
            name="code_pass_rate_low",
            condition=lambda s: self._get_metric_value(s, "code_pass_rate") < 0.90,
            severity=AlertSeverity.WARNING,
            title="代码级检查通过率低",
            message="代码级检查（工具调用、格式等）通过率低于 90%。建议检查基础功能。"
        ))
        
        # 6. 模型级检查通过率低
        self.add_rule(AlertRule(
            name="model_pass_rate_low",
            condition=lambda s: self._get_metric_value(s, "model_pass_rate") < 0.70,
            severity=AlertSeverity.WARNING,
            title="模型级检查通过率低",
            message="模型级检查（意图理解、质量等）通过率低于 70%。建议优化 prompt 或模型配置。"
        ))
        
        # 7. 平均质量得分低
        self.add_rule(AlertRule(
            name="quality_score_low",
            condition=lambda s: self._get_metric_value(s, "avg_quality_score") < 6.0,
            severity=AlertSeverity.WARNING,
            title="平均质量得分低",
            message="LLM-as-Judge 平均质量得分低于 6.0/10。建议人工复审低分案例。"
        ))
        
        # 8. 错误率过高
        self.add_rule(AlertRule(
            name="error_rate_high",
            condition=lambda s: self._get_metric_value(s, "error_rate") > 0.10,
            severity=AlertSeverity.CRITICAL,
            title="错误率过高",
            message="执行错误率超过 10%，系统稳定性存在问题。建议检查异常处理和容错机制。"
        ))
        
        # 9. 平均执行时间过长
        self.add_rule(AlertRule(
            name="execution_time_high",
            condition=lambda s: self._get_metric_value(s, "avg_execution_time") > 60.0,
            severity=AlertSeverity.WARNING,
            title="平均执行时间过长",
            message="平均执行时间超过 60 秒，可能影响用户体验。建议优化性能。"
        ))
        
        # 10. 人工复审比例过高
        self.add_rule(AlertRule(
            name="human_review_rate_high",
            condition=lambda s: self._get_metric_value(s, "human_review_rate") > 0.25,
            severity=AlertSeverity.INFO,
            title="人工复审比例过高",
            message="需要人工复审的评分超过 25%，LLM-as-Judge 置信度不足。建议优化 grader prompt。"
        ))
    
    def add_rule(self, rule: AlertRule) -> None:
        """添加告警规则"""
        self.rules.append(rule)
    
    def add_notifier(self, notifier: Callable[[List[Alert]], None]) -> None:
        """
        添加通知器
        
        Args:
            notifier: 通知函数，接收告警列表并发送通知
        """
        self.notifiers.append(notifier)
    
    def check_all(self, summary: MetricSummary) -> List[Alert]:
        """
        检查所有告警规则
        
        Args:
            summary: 指标汇总
            
        Returns:
            触发的告警列表
        """
        alerts = []
        for rule in self.rules:
            alert = rule.check(summary)
            if alert:
                alerts.append(alert)
        return alerts
    
    def notify(self, alerts: List[Alert]) -> None:
        """
        发送告警通知
        
        Args:
            alerts: 告警列表
        """
        if not alerts:
            return
        
        for notifier in self.notifiers:
            try:
                notifier(alerts)
            except Exception as e:
                print(f"⚠️  通知发送失败: {e}")
    
    def process(self, summary: MetricSummary) -> List[Alert]:
        """
        处理评估结果，检查并发送告警
        
        Args:
            summary: 指标汇总
            
        Returns:
            触发的告警列表
        """
        alerts = self.check_all(summary)
        self.notify(alerts)
        return alerts
    
    @staticmethod
    def _get_metric_value(summary: MetricSummary, metric_name: str) -> float:
        """获取指标值"""
        metric = next((m for m in summary.metrics if m.name == metric_name), None)
        return metric.value if metric else 0.0


# ========== 通知器实现 ==========

def console_notifier(alerts: List[Alert]) -> None:
    """控制台通知器（打印到终端）"""
    severity_icons = {
        AlertSeverity.CRITICAL: "🔴",
        AlertSeverity.WARNING: "🟡",
        AlertSeverity.INFO: "🔵"
    }
    
    print("\n" + "=" * 80)
    print("评估告警通知")
    print("=" * 80)
    
    for alert in alerts:
        icon = severity_icons.get(alert.severity, "⚪")
        print(f"\n{icon} [{alert.severity.upper()}] {alert.title}")
        print(f"   {alert.message}")
        if alert.metric_name:
            print(f"   指标: {alert.metric_name}")
            print(f"   当前值: {alert.current_value}")
            print(f"   阈值: {alert.threshold}")
        print(f"   时间: {alert.timestamp}")
    
    print("\n" + "=" * 80 + "\n")


def slack_notifier(webhook_url: str) -> Callable[[List[Alert]], None]:
    """
    Slack 通知器工厂函数
    
    Args:
        webhook_url: Slack Webhook URL
        
    Returns:
        通知函数
    """
    def notifier(alerts: List[Alert]) -> None:
        import requests
        
        severity_colors = {
            AlertSeverity.CRITICAL: "#FF0000",  # 红色
            AlertSeverity.WARNING: "#FFA500",   # 橙色
            AlertSeverity.INFO: "#0000FF"       # 蓝色
        }
        
        # 构建 Slack 消息
        attachments = []
        for alert in alerts:
            attachments.append({
                "color": severity_colors.get(alert.severity, "#808080"),
                "title": f"[{alert.severity.upper()}] {alert.title}",
                "text": alert.message,
                "footer": f"ZenFlux Agent 评估系统",
                "ts": int(datetime.fromisoformat(alert.timestamp.replace("Z", "+00:00")).timestamp())
            })
        
        payload = {
            "text": f"🚨 发现 {len(alerts)} 个评估告警",
            "attachments": attachments
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"✅ Slack 通知已发送（{len(alerts)} 个告警）")
    
    return notifier


def email_notifier(
    smtp_server: str,
    smtp_port: int,
    sender: str,
    password: str,
    recipients: List[str]
) -> Callable[[List[Alert]], None]:
    """
    邮件通知器工厂函数
    
    Args:
        smtp_server: SMTP 服务器地址
        smtp_port: SMTP 端口
        sender: 发件人邮箱
        password: 发件人密码
        recipients: 收件人列表
        
    Returns:
        通知函数
    """
    def notifier(alerts: List[Alert]) -> None:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # 构建邮件
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"ZenFlux Agent 评估告警 ({len(alerts)} 个)"
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        
        # 构建邮件正文
        lines = ["<html><body>"]
        lines.append("<h2>ZenFlux Agent 评估告警</h2>")
        lines.append(f"<p>发现 {len(alerts)} 个告警，详情如下：</p>")
        
        for i, alert in enumerate(alerts, 1):
            severity_color = {
                AlertSeverity.CRITICAL: "red",
                AlertSeverity.WARNING: "orange",
                AlertSeverity.INFO: "blue"
            }.get(alert.severity, "gray")
            
            lines.append(f"<div style='border-left: 4px solid {severity_color}; padding-left: 10px; margin: 10px 0;'>")
            lines.append(f"<h3>{i}. [{alert.severity.upper()}] {alert.title}</h3>")
            lines.append(f"<p>{alert.message}</p>")
            lines.append(f"<small>时间: {alert.timestamp}</small>")
            lines.append("</div>")
        
        lines.append("</body></html>")
        html_content = "\n".join(lines)
        
        msg.attach(MIMEText(html_content, "html"))
        
        # 发送邮件
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        
        print(f"✅ 邮件通知已发送到 {len(recipients)} 个收件人")
    
    return notifier


def file_notifier(log_file: str) -> Callable[[List[Alert]], None]:
    """
    文件通知器工厂函数（写入日志文件）
    
    Args:
        log_file: 日志文件路径
        
    Returns:
        通知函数
    """
    def notifier(alerts: List[Alert]) -> None:
        import json
        from pathlib import Path
        
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取现有日志
        existing_logs = []
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8") as f:
                try:
                    existing_logs = json.load(f)
                except json.JSONDecodeError:
                    existing_logs = []
        
        # 添加新告警
        for alert in alerts:
            existing_logs.append({
                "severity": alert.severity,
                "title": alert.title,
                "message": alert.message,
                "metric_name": alert.metric_name,
                "current_value": alert.current_value,
                "threshold": alert.threshold,
                "timestamp": alert.timestamp
            })
        
        # 写入文件
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(existing_logs, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 告警已记录到 {log_file}（{len(alerts)} 个）")
    
    return notifier
