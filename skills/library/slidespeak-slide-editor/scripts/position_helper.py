#!/usr/bin/env python3
"""
位置索引计算辅助工具

帮助计算 SlideSpeak API 的实际 position 索引
"""

def calculate_position(
    user_page_number: int,
    has_cover: bool = True,
    has_toc: bool = True
) -> int:
    """
    计算实际的 position 索引
    
    Args:
        user_page_number: 用户说的页码（1-based，从"第1页内容"开始）
        has_cover: 是否有封面
        has_toc: 是否有目录
    
    Returns:
        实际的 position 索引（0-based）
    
    Examples:
        >>> calculate_position(1, has_cover=True, has_toc=True)
        2  # 封面(0) + 目录(1) + 第1页内容(2)
        
        >>> calculate_position(3, has_cover=True, has_toc=False)
        3  # 封面(0) + 第1页内容(1) + 第2页内容(2) + 第3页内容(3)
        
        >>> calculate_position(1, has_cover=False, has_toc=False)
        0  # 直接是第1页内容(0)
    """
    if user_page_number < 1:
        raise ValueError("user_page_number must be >= 1")
    
    offset = 0
    if has_cover:
        offset += 1
    if has_toc:
        offset += 1
    
    return user_page_number - 1 + offset


def reverse_position(
    position: int,
    has_cover: bool = True,
    has_toc: bool = True
) -> dict:
    """
    反向计算：从 position 索引到用户页码
    
    Args:
        position: API 的 position 索引（0-based）
        has_cover: 是否有封面
        has_toc: 是否有目录
    
    Returns:
        包含页面信息的字典
    
    Examples:
        >>> reverse_position(2, has_cover=True, has_toc=True)
        {'position': 2, 'type': 'content', 'user_page': 1}
        
        >>> reverse_position(0, has_cover=True, has_toc=True)
        {'position': 0, 'type': 'cover', 'user_page': None}
    """
    offset = 0
    if has_cover:
        offset += 1
    if has_toc:
        offset += 1
    
    # 判断页面类型
    if has_cover and position == 0:
        return {
            "position": position,
            "type": "cover",
            "user_page": None,
            "description": "封面页（不可编辑）"
        }
    
    if has_toc and position == (1 if has_cover else 0):
        return {
            "position": position,
            "type": "toc",
            "user_page": None,
            "description": "目录页（不可编辑）"
        }
    
    # 内容页
    user_page = position - offset + 1
    return {
        "position": position,
        "type": "content",
        "user_page": user_page,
        "description": f"第{user_page}页内容"
    }


def print_position_map(total_slides: int, has_cover: bool = True, has_toc: bool = True):
    """
    打印完整的位置映射表
    
    Args:
        total_slides: PPT 总页数
        has_cover: 是否有封面
        has_toc: 是否有目录
    """
    print("\n" + "="*60)
    print(f"📊 位置索引映射表 (总页数: {total_slides})")
    print("="*60)
    print(f"配置: 封面={'✅' if has_cover else '❌'}  目录={'✅' if has_toc else '❌'}")
    print("-"*60)
    print(f"{'Position':<10} {'类型':<12} {'用户页码':<12} {'说明'}")
    print("-"*60)
    
    for position in range(total_slides):
        info = reverse_position(position, has_cover, has_toc)
        
        type_icon = {
            "cover": "📄",
            "toc": "📑",
            "content": "📝"
        }.get(info["type"], "❓")
        
        user_page_str = f"第{info['user_page']}页" if info["user_page"] else "N/A"
        editable = "✏️  可编辑" if info["type"] == "content" else "🔒 不可编辑"
        
        print(f"{position:<10} {type_icon} {info['type']:<10} {user_page_str:<12} {editable}")
    
    print("="*60 + "\n")


def get_insert_position_suggestion(
    user_instruction: str,
    total_slides: int,
    has_cover: bool = True,
    has_toc: bool = True
) -> dict:
    """
    根据用户指令建议插入位置
    
    Args:
        user_instruction: 用户指令（如"在第3页后添加"）
        total_slides: 当前 PPT 总页数
        has_cover: 是否有封面
        has_toc: 是否有目录
    
    Returns:
        建议的位置信息
    """
    import re
    
    # 匹配"第X页"
    match = re.search(r'第(\d+)页', user_instruction)
    
    if match:
        user_page = int(match.group(1))
        
        # 判断是"在第X页后"还是"在第X页前"
        if "后" in user_instruction or "之后" in user_instruction:
            # 在第X页后 = X+1的位置
            position = calculate_position(user_page + 1, has_cover, has_toc)
            description = f"在第{user_page}页后插入 → position={position}"
        elif "前" in user_instruction or "之前" in user_instruction:
            # 在第X页前 = X的位置
            position = calculate_position(user_page, has_cover, has_toc)
            description = f"在第{user_page}页前插入 → position={position}"
        else:
            # 默认理解为"在第X页后"
            position = calculate_position(user_page + 1, has_cover, has_toc)
            description = f"在第{user_page}页后插入 → position={position}（默认理解为'后'）"
        
        return {
            "position": position,
            "description": description,
            "confidence": "high"
        }
    
    # 匹配"最后"、"末尾"
    if "最后" in user_instruction or "末尾" in user_instruction:
        return {
            "position": total_slides,
            "description": f"在最后添加 → position={total_slides}",
            "confidence": "high"
        }
    
    # 匹配"开头"、"最前"
    if "开头" in user_instruction or "最前" in user_instruction:
        offset = 0
        if has_cover:
            offset += 1
        if has_toc:
            offset += 1
        return {
            "position": offset,
            "description": f"在内容开头添加 → position={offset}",
            "confidence": "medium"
        }
    
    return {
        "position": None,
        "description": "无法确定位置，请明确指定",
        "confidence": "low"
    }


if __name__ == "__main__":
    print("\n🔧 SlideSpeak 位置索引计算工具\n")
    
    # 示例1: 标准配置（封面 + 目录）
    print("示例1: 标准配置（封面 + 目录）")
    print_position_map(10, has_cover=True, has_toc=True)
    
    # 示例2: 无目录
    print("\n示例2: 无目录配置")
    print_position_map(8, has_cover=True, has_toc=False)
    
    # 示例3: 测试计算
    print("\n示例3: 位置计算测试")
    test_cases = [
        ("第1页", 1, True, True),
        ("第3页", 3, True, True),
        ("第5页", 5, True, False),
        ("第1页", 1, False, False),
    ]
    
    for desc, page, cover, toc in test_cases:
        position = calculate_position(page, cover, toc)
        print(f"{desc} (封面={cover}, 目录={toc}) → position = {position}")
    
    # 示例4: 用户指令解析
    print("\n示例4: 用户指令解析")
    instructions = [
        "在第3页后添加一页",
        "在第5页前插入新内容",
        "在最后添加总结",
        "在开头添加简介"
    ]
    
    for instruction in instructions:
        result = get_insert_position_suggestion(instruction, total_slides=10)
        print(f"'{instruction}' → {result['description']}")

