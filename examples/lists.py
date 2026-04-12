def sum_list(nums: list[int]) -> int:
    total: int = 0
    for n in range(len(nums)):
        total = total + nums[n]
    return total


def main() -> int:
    numbers: list[int] = [1, 2, 3, 4, 5]
    result: int = sum_list(numbers)
    print(result)
    return 0
