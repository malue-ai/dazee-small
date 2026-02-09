"""
SlideSpeak Configuration Validator
验证配置是否符合官方API规范

Reference: https://docs.slidespeak.co/basics/api-references/slide-by-slide/
"""

import json
import sys
from typing import Dict, List, Tuple, Any


# ==================== 官方API硬性约束 ====================
# Source: https://docs.slidespeak.co/basics/api-references/slide-by-slide/

FIXED_ITEM_AMOUNT_LAYOUTS = {
    'COMPARISON': 2,   # comparison layout requires exactly 2 items
    'SWOT': 4,         # swot layout requires exactly 4 items  
    'PESTEL': 6,       # pestel layout requires exactly 6 items
    'THANKS': 0        # thanks layout requires 0 items
}


def validate_slidespeak_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    验证SlideSpeak配置是否符合官方API规范
    
    只检查API文档明确要求的约束
    """
    errors = []
    
    # 1. 必需字段
    if 'template' not in config:
        errors.append("Missing required field: 'template'")
    
    if 'slides' not in config:
        errors.append("Missing required field: 'slides'")
        return False, errors
    
    if not isinstance(config['slides'], list) or len(config['slides']) == 0:
        errors.append("Field 'slides' must be a non-empty array")
        return False, errors
    
    # 2. 验证每个slide
    for i, slide in enumerate(config['slides'], 1):
        slide_errors = validate_slide(slide, i)
        errors.extend(slide_errors)
    
    return len(errors) == 0, errors


def validate_slide(slide: Dict[str, Any], index: int) -> List[str]:
    """验证单个slide是否符合API规范"""
    errors = []
    prefix = f"Slide #{index}:"
    
    # 必需字段
    required_fields = ['title', 'item_amount', 'content']
    for field in required_fields:
        if field not in slide:
            errors.append(f"{prefix} Missing required field '{field}'")
    
    # layout or layout_name (二选一)
    has_layout = 'layout' in slide
    has_layout_name = 'layout_name' in slide
    
    if not has_layout and not has_layout_name:
        errors.append(f"{prefix} Must specify either 'layout' or 'layout_name'")
    elif has_layout and has_layout_name:
        errors.append(f"{prefix} Cannot specify both 'layout' and 'layout_name' (mutually exclusive)")
    
    # 检查固定item_amount约束
    if 'layout' in slide and 'item_amount' in slide:
        layout = slide['layout'].upper() if isinstance(slide['layout'], str) else ''
        item_amount = slide['item_amount']
        
        if layout in FIXED_ITEM_AMOUNT_LAYOUTS:
            required_amount = FIXED_ITEM_AMOUNT_LAYOUTS[layout]
            if item_amount != required_amount:
                errors.append(
                    f"{prefix} Layout '{layout}' requires exactly {required_amount} items "
                    f"(got {item_amount}). "
                    f"Source: https://docs.slidespeak.co/basics/api-references/slide-by-slide/"
                )
    
    # 检查content类型
    if 'content' in slide and not isinstance(slide['content'], str):
        errors.append(
            f"{prefix} Field 'content' must be a string "
            f"(got {type(slide['content']).__name__})"
        )
    
    # TABLE layout特殊要求
    if 'layout' in slide and slide['layout'].upper() == 'TABLE':
        if 'table' not in slide:
            errors.append(
                f"{prefix} TABLE layout requires 'table' field "
                "(array of rows where first row is header)"
            )
    
    return errors


def main():
    """命令行入口"""
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            config_json = f.read()
    else:
        config_json = sys.stdin.read()
    
    try:
        config = json.loads(config_json)
        is_valid, errors = validate_slidespeak_config(config)
        
        if is_valid:
            print("✅ Configuration is valid")
            print(f"   Slides: {len(config.get('slides', []))}")
            print(f"   Template: {config.get('template', 'N/A')}")
            return 0
        else:
            print("❌ Configuration validation failed:")
            for error in errors:
                print(f"   • {error}")
            print("\n📚 Reference: https://docs.slidespeak.co/basics/api-references/slide-by-slide/")
            return 1
            
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
