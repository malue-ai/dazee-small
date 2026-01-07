#!/usr/bin/env python3
"""
计算1到100的和
"""

# 方法1: 使用循环
def sum_with_loop():
    total = 0
    for i in range(1, 101):
        total += i
    return total

# 方法2: 使用内置sum函数
def sum_with_builtin():
    return sum(range(1, 101))

# 方法3: 使用数学公式 n(n+1)/2
def sum_with_formula(n=100):
    return n * (n + 1) // 2

if __name__ == "__main__":
    print("计算1到100的和:")
    print("-" * 40)
    
    result1 = sum_with_loop()
    print(f"方法1 (循环): {result1}")
    
    result2 = sum_with_builtin()
    print(f"方法2 (内置函数): {result2}")
    
    result3 = sum_with_formula()
    print(f"方法3 (数学公式): {result3}")
    
    print("-" * 40)
    print(f"✓ 所有方法结果一致: {result1 == result2 == result3}")
