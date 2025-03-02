import re

def mask_numbers(text: str) -> str:
    """
    将字符串中的数字替换为 123
    
    Args:
        text: 需要脱敏的字符串
    
    Returns:
        脱敏后的字符串
    
    Examples:
        >>> mask_numbers("我的电话是13812345678")
        '我的电话是123123123123'
        >>> mask_numbers("股票代码600123涨幅5.6%")
        '股票代码123123涨幅123.123%'
    """
    # 使用正则表达式匹配数字（包括小数点）
    pattern = r'\d+\.?\d*'
    return re.sub(pattern, '123', text)

if __name__ == "__main__":
    # 测试用例
    test_cases = [
        """"""
    ]
    
    for test in test_cases:
        masked = mask_numbers(test)
        # print(f"原始字符串: {test}")
        print(f"脱敏结果: {masked}")
        print("-" * 40)