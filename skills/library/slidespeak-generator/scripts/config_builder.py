"""
SlideSpeak Configuration Builder
基于官方API规范生成配置

Reference: https://docs.slidespeak.co/basics/api-references/slide-by-slide/
"""

import json
import sys
from typing import Dict, List, Any, Tuple


# ==================== 官方API硬性约束 ====================
# Source: https://docs.slidespeak.co/basics/api-references/slide-by-slide/
# Note: "The item_amount parameter must respect the item range constraints for each layout type"

FIXED_ITEM_AMOUNT_LAYOUTS = {
    'COMPARISON': 2,   # comparison layout requires exactly 2 items
    'SWOT': 4,         # swot layout requires exactly 4 items
    'PESTEL': 6,       # pestel layout requires exactly 6 items
    'THANKS': 0        # thanks layout requires 0 items
}


def validate_api_constraints(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    验证是否符合官方API硬性约束
    
    只检查API文档明确要求的约束，不添加额外限制
    """
    errors = []
    
    # 检查必需字段
    if 'template' not in config:
        errors.append("Missing required field: 'template'")
    
    if 'slides' not in config or not config['slides']:
        errors.append("Missing or empty required field: 'slides'")
        return False, errors
    
    # 检查每个slide
    for idx, slide in enumerate(config['slides'], 1):
        # 必需字段
        required_fields = ['title', 'item_amount', 'content']
        for field in required_fields:
            if field not in slide:
                errors.append(f"Slide #{idx}: Missing required field '{field}'")
        
        # layout or layout_name (二选一)
        if 'layout' not in slide and 'layout_name' not in slide:
            errors.append(f"Slide #{idx}: Must specify either 'layout' or 'layout_name'")
        
        # 检查固定item_amount约束
        layout = slide.get('layout', '').upper()
        item_amount = slide.get('item_amount')
        
        if layout in FIXED_ITEM_AMOUNT_LAYOUTS:
            required_amount = FIXED_ITEM_AMOUNT_LAYOUTS[layout]
            if item_amount != required_amount:
                errors.append(
                    f"Slide #{idx}: Layout '{layout}' requires exactly {required_amount} items "
                    f"(got {item_amount}). Source: SlideSpeak API documentation"
                )
    
    return len(errors) == 0, errors


def build_slidespeak_config(requirements: Dict[str, Any]) -> Dict[str, Any]:
    """
    基于用户需求生成SlideSpeak配置
    
    这只是一个简单的示例生成器，实际使用时应该由AI基于内容智能生成
    """
    topic = requirements.get("topic", "Presentation")
    pages = requirements.get("pages", 6)
    language = requirements.get("language", "ORIGINAL")
    
    config = {
        "template": "DEFAULT",
        "language": language,
        "fetch_images": True,
        "slides": []
    }
    
    # 生成示例slides
    for i in range(pages):
        if i == 0:
            slide = {
                "title": f"{topic} - Overview",
                "layout": "ITEMS",
                "item_amount": 3,
                "content": f"Key points about {topic}"
            }
        elif i == pages - 1:
            slide = {
                "title": "Thank You",
                "layout": "THANKS",
                "item_amount": 0,  # API requirement
                "content": "Contact information and next steps"
            }
        else:
            slide = {
                "title": f"{topic} - Part {i}",
                "layout": "ITEMS",
                "item_amount": 4,
                "content": f"Detailed content for part {i}"
            }
        
        config["slides"].append(slide)
    
    return config


def main():
    """命令行入口"""
    if len(sys.argv) > 1:
        requirements_json = sys.argv[1]
    else:
        requirements_json = sys.stdin.read()
    
    try:
        requirements = json.loads(requirements_json)
        config = build_slidespeak_config(requirements)
        
        # 验证API约束
        is_valid, errors = validate_api_constraints(config)
        
        if not is_valid:
            print("API constraint validation failed:", file=sys.stderr)
            for error in errors:
                print(f"  • {error}", file=sys.stderr)
            return 1
        
        # 输出配置
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
