def main() -> int:
    nums = [1, 2, 3]
    chars = ["a", "b", "c"]
    
    # 1. zip
    for n, c in zip(nums, chars):
        print(n)
        print(c)
        
    # 2. enumerate
    for i, n in enumerate(nums):
        print(i)
        print(n)
        
    # 3. map
    doubled = map(lambda x: x * 2, nums)
    # Note: map returns an iterator, need to iterate or collect
    for d in doubled:
        print(d)
        
    # 4. reversed
    for r in reversed(nums):
        print(r)
        
    return 0
