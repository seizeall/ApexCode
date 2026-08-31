"""
冒泡排序算法实现
"""


def bubble_sort(arr: list) -> list:
    """
    对列表进行冒泡排序（原地排序）
    
    Args:
        arr: 要排序的列表
    
    Returns:
        排序后的列表（原地修改）
    
    Time Complexity: O(n^2)
    Space Complexity: O(1)
    """
    n = len(arr)
    
    # 遍历所有元素
    for i in range(n):
        # 标记是否发生交换，用于优化
        swapped = False
        
        # 最后i个元素已经排好序，无需比较
        for j in range(0, n - i - 1):
            # 如果当前元素大于下一个元素，则交换
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        
        # 如果这一轮没有发生交换，说明已经有序
        if not swapped:
            break
    
    return arr


def bubble_sort_with_trace(arr: list) -> list:
    """
    带调试信息的冒泡排序，便于理解算法过程
    """
    n = len(arr)
    print(f"原始数组: {arr}")
    
    for i in range(n):
        swapped = False
        print(f"\n第 {i + 1} 轮:")
        
        for j in range(0, n - i - 1):
            print(f"  比较 arr[{j}]={arr[j]} 和 arr[{j + 1}]={arr[j + 1]}", end="")
            
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
                print(f" -> 交换后: {arr}")
            else:
                print(" -> 无需交换")
        
        print(f"本轮结果: {arr}")
        
        if not swapped:
            print("本轮无交换，数组已有序，提前结束")
            break
    
    return arr


if __name__ == "__main__":
    # 测试用例
    test_cases = [
        [64, 34, 25, 12, 22, 11, 90],
        [5, 1, 4, 2, 8],
        [1, 2, 3, 4, 5],  # 已排序
        [5, 4, 3, 2, 1],  # 逆序
        [1],              # 单个元素
        [],               # 空数组
    ]
    
    print("冒泡排序测试:")
    print("=" * 50)
    
    for i, test_arr in enumerate(test_cases):
        original = test_arr.copy()
        sorted_arr = bubble_sort(test_arr)
        print(f"测试 {i + 1}: {original} -> {sorted_arr}")
    
    print("\n" + "=" * 50)
    print("带调试信息的冒泡排序示例:")
    bubble_sort_with_trace([5, 3, 8, 4, 2])