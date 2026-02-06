"""
飞书卡片构建器

构建各类飞书卡片消息
"""

from typing import Dict, Any, List, Optional


class FeishuCardBuilder:
    """
    飞书卡片构建器
    
    使用示例：
    ```python
    # 构建简单文本卡片
    card = FeishuCardBuilder.text_card("标题", "内容")
    
    # 构建带按钮的卡片
    card = FeishuCardBuilder.confirmation_card(
        title="确认操作",
        content="是否继续？",
        confirm_text="确认",
        cancel_text="取消",
        request_id="req-001"
    )
    
    # 构建流式输出卡片
    card = FeishuCardBuilder.streaming_card("正在思考...", is_typing=True)
    ```
    """
    
    @staticmethod
    def text_card(
        title: str,
        content: str,
        template: str = "blue"
    ) -> Dict[str, Any]:
        """
        构建文本卡片
        
        Args:
            title: 标题
            content: 内容（支持 Markdown）
            template: 主题色
            
        Returns:
            卡片数据
        """
        return {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": template
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                }
            ]
        }
    
    @staticmethod
    def confirmation_card(
        title: str,
        content: str,
        confirm_text: str = "确认",
        cancel_text: str = "取消",
        request_id: str = "",
        description: str = ""
    ) -> Dict[str, Any]:
        """
        构建确认卡片
        
        Args:
            title: 标题
            content: 内容
            confirm_text: 确认按钮文本
            cancel_text: 取消按钮文本
            request_id: 请求 ID
            description: 描述
            
        Returns:
            卡片数据
        """
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content
                }
            }
        ]
        
        if description:
            elements.append({
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": description}
                ]
            })
        
        # 添加按钮
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": confirm_text},
                    "type": "primary",
                    "value": {"action": "confirm", "request_id": request_id}
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": cancel_text},
                    "type": "danger",
                    "value": {"action": "cancel", "request_id": request_id}
                }
            ]
        })
        
        return {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": elements
        }
    
    @staticmethod
    def streaming_card(
        content: str,
        is_typing: bool = False,
        title: str = "回复中..."
    ) -> Dict[str, Any]:
        """
        构建流式输出卡片
        
        Args:
            content: 当前内容
            is_typing: 是否显示打字指示器
            title: 标题
            
        Returns:
            卡片数据
        """
        display_content = content
        if is_typing:
            display_content += " ▌"  # 打字光标
        
        return {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": display_content or "..."
                    }
                }
            ]
        }
    
    @staticmethod
    def error_card(
        error_type: str,
        error_message: str
    ) -> Dict[str, Any]:
        """
        构建错误卡片
        
        Args:
            error_type: 错误类型
            error_message: 错误信息
            
        Returns:
            卡片数据
        """
        return {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"❌ 错误: {error_type}"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": error_message
                    }
                }
            ]
        }
    
    @staticmethod
    def status_card(
        title: str,
        fields: List[Dict[str, str]],
        template: str = "green"
    ) -> Dict[str, Any]:
        """
        构建状态卡片
        
        Args:
            title: 标题
            fields: 字段列表 [{"label": "...", "value": "..."}]
            template: 主题色
            
        Returns:
            卡片数据
        """
        field_elements = [
            {
                "is_short": True,
                "text": {
                    "tag": "lark_md",
                    "content": f"**{f['label']}**\n{f['value']}"
                }
            }
            for f in fields
        ]
        
        return {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": template
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": field_elements
                }
            ]
        }
    
    @staticmethod
    def options_card(
        title: str,
        content: str,
        options: List[Dict[str, str]],
        request_id: str = ""
    ) -> Dict[str, Any]:
        """
        构建选项卡片
        
        Args:
            title: 标题
            content: 内容
            options: 选项列表 [{"label": "...", "value": "..."}]
            request_id: 请求 ID
            
        Returns:
            卡片数据
        """
        buttons = []
        for i, opt in enumerate(options[:4]):  # 最多 4 个按钮
            btn_type = "primary" if i == 0 else "default"
            buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": opt["label"]},
                "type": btn_type,
                "value": {"action": "select", "option": opt["value"], "request_id": request_id}
            })
        
        return {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                },
                {
                    "tag": "action",
                    "actions": buttons
                }
            ]
        }
    
    @staticmethod
    def final_card(
        title: str,
        content: str,
        template: str = "green"
    ) -> Dict[str, Any]:
        """
        构建最终回复卡片（流式输出结束）
        
        Args:
            title: 标题
            content: 内容
            template: 主题色
            
        Returns:
            卡片数据
        """
        return {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": template
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                }
            ]
        }
