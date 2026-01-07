#!/usr/bin/env python3
"""
计算 1 到 100 的和
"""

def calculate_sum(start, end):
    """
    计算从 start 到 end 的整数和
    
    Args:
        start: 起始数字
        end: 结束数字
    
    Returns:
        整数和
    """
    return sum(range(start, end + 1))


def main():
    # 方法1: 使用 sum 和 range
    result1 = sum(range(1, 101))
    print(f"方法1 (使用 sum): 1 到 100 的和 = {result1}")
    
    # 方法2: 使用函数
    result2 = calculate_sum(1, 100)
    print(f"方法2 (使用函数): 1 到 100 的和 = {result2}")
    
    # 方法3: 使用数学公式 (高斯求和公式: n*(n+1)/2)
    n = 100
    result3 = n * (n + 1) // 2
    print(f"方法3 (高斯公式): 1 到 100 的和 = {result3}")
    
    # 方法4: 使用循环
    result4 = 0
    for i in range(1, 101):
        result4 += i
    print(f"方法4 (使用循环): 1 到 100 的和 = {result4}")


if __name__ == "__main__":
    main()
