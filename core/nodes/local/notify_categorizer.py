# -*- coding: utf-8 -*-
"""
通知分类系统

多层次管道：
  1. 结构化元数据（调用方传入 category 字段）→ 最高优先级
     LLM-First：Agent 在调用 notify 时通过 category 参数声明类别
  2. 用户自定义规则（notify-rules.json，正则或关键词）
  3. 默认 info 类别

每个类别映射不同的 Toast 模板参数（图标、优先级、声音等）。
用户可通过 notify-rules.json 自定义过滤开关，实现按类别屏蔽通知。
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 每个 category 的展示属性（调用方通过 category 字段声明，不做关键词猜测）
CATEGORY_META: Dict[str, Dict[str, Any]] = {
    "health":   {"icon": "🩸", "priority": "high",   "sound": True},
    "urgent":   {"icon": "🚨", "priority": "high",   "sound": True},
    "reminder": {"icon": "⏰", "priority": "normal", "sound": True},
    "email":    {"icon": "📧", "priority": "normal", "sound": False},
    "calendar": {"icon": "📅", "priority": "normal", "sound": True},
    "error":    {"icon": "⚠️", "priority": "high",   "sound": True},
    "build":    {"icon": "🔨", "priority": "normal", "sound": False},
    "stock":    {"icon": "📦", "priority": "normal", "sound": False},
    "info":     {"icon": "🤖", "priority": "low",    "sound": False},
}


@dataclass
class UserRule:
    """用户自定义分类规则"""

    pattern: str
    category: str
    is_regex: bool = False
    enabled: bool = True
    _compiled: Optional[re.Pattern] = field(default=None, repr=False, compare=False)

    def matches(self, text: str) -> bool:
        if not self.enabled:
            return False
        try:
            if self.is_regex:
                if self._compiled is None:
                    self._compiled = re.compile(self.pattern, re.IGNORECASE)
                return bool(self._compiled.search(text))
            else:
                return self.pattern.lower() in text.lower()
        except re.error:
            return False


@dataclass
class CategoryResult:
    """分类结果"""

    category: str
    icon: str
    priority: str  # high / normal / low
    sound: bool
    source: str    # "metadata" / "user_rule" / "keyword" / "default"


class NotificationCategorizer:
    """
    通知分类器

    使用方式：
        categorizer = NotificationCategorizer(data_dir)
        result = categorizer.categorize(title, message, category="urgent")
        if categorizer.should_show(result.category):
            ...
    """

    def __init__(self, data_dir: str) -> None:
        self._rules_path = os.path.join(data_dir, "notify-rules.json")
        self._user_rules: List[UserRule] = []
        self._settings: Dict[str, Any] = self._default_settings()
        self._load()

    # ── 公共 API ──────────────────────────────────────────────────────────────

    def categorize(
        self,
        title: str,
        message: str,
        category: Optional[str] = None,
    ) -> CategoryResult:
        """
        对通知进行分类。

        Args:
            title: 通知标题
            message: 通知正文
            category: 调用方传入的结构化类别（最高优先级）

        Returns:
            CategoryResult
        """
        combined = f"{title} {message}"

        # 第 1 层：结构化元数据
        if category and category in CATEGORY_META:
            return self._make_result(category, "metadata")

        # 第 2 层：用户自定义规则
        for rule in self._user_rules:
            if rule.matches(combined):
                cat = rule.category if rule.category in CATEGORY_META else "info"
                return self._make_result(cat, "user_rule")

        # 第 3 层：默认（不做关键词猜测，LLM 应在调用时通过 category 声明）
        return self._make_result("info", "default")

    def should_show(self, category: str) -> bool:
        """根据用户设置判断该类别通知是否显示"""
        if not self._settings.get("showNotifications", True):
            return False
        key = f"notify{category.capitalize()}"
        return bool(self._settings.get(key, True))

    def get_settings(self) -> Dict[str, Any]:
        return dict(self._settings)

    def update_settings(self, new_settings: Dict[str, Any]) -> None:
        self._settings.update(new_settings)
        self._save()

    # ── 内部 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_result(category: str, source: str) -> CategoryResult:
        meta = CATEGORY_META.get(category, CATEGORY_META["info"])
        return CategoryResult(
            category=category,
            icon=meta["icon"],
            priority=meta["priority"],
            sound=meta["sound"],
            source=source,
        )

    @staticmethod
    def _default_settings() -> Dict[str, Any]:
        return {
            "showNotifications": True,
            "notifyChatResponses": True,
            "notifyHealth": True,
            "notifyUrgent": True,
            "notifyReminder": True,
            "notifyEmail": True,
            "notifyCalendar": True,
            "notifyError": True,
            "notifyBuild": True,
            "notifyStock": True,
            "notifyInfo": True,
        }

    def _load(self) -> None:
        if not os.path.isfile(self._rules_path):
            self._save()
            return
        try:
            with open(self._rules_path, encoding="utf-8") as f:
                data = json.load(f)
            self._settings.update(data.get("settings", {}))
            self._user_rules = [
                UserRule(
                    pattern=r["pattern"],
                    category=r.get("category", "info"),
                    is_regex=r.get("isRegex", False),
                    enabled=r.get("enabled", True),
                )
                for r in data.get("userRules", [])
            ]
            logger.debug(f"[NOTIFY] 加载 {len(self._user_rules)} 条用户通知规则")
        except Exception as e:
            logger.warning(f"[NOTIFY] 加载通知规则失败: {e}")

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._rules_path), exist_ok=True)
            data = {
                "settings": self._settings,
                "userRules": [
                    {
                        "pattern": r.pattern,
                        "category": r.category,
                        "isRegex": r.is_regex,
                        "enabled": r.enabled,
                    }
                    for r in self._user_rules
                ],
            }
            with open(self._rules_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[NOTIFY] 保存通知规则失败: {e}")
