def main() -> int:
    # 1. Lambdas
    add = lambda x, y: x + y
    print(add(10, 20))
    
    # 2. List comprehension
    nums: list[int] = [1, 2, 3, 4, 5, 6]
    evens: list[int] = [x for x in nums if x % 2 == 0]
    print(evens) # [2, 4, 6]
    
    # 3. List comprehension with operation
    squares: list[int] = [x * x for x in nums]
    print(squares) # [1, 4, 9, 16, 25, 36]
    
    # 4. Nested comprehension
    xs: list[int] = [1, 2]
    ys: list[int] = [10, 20]
    # Note: Tuple literal was implemented in previous waves
    pairs: list[tuple[int, int]] = [(x, y) for x in xs for y in ys]
    print(pairs) # [(1, 10), (1, 20), (2, 10), (2, 20)]
    
    # 5. Set comprehension
    # Currently py2rust maps {} to HashSet
    # {1, 2, 1} -> {1, 2}
    unique_nums: set[int] = {x % 3 for x in nums}
    # print behavior for HashSet might be tricky in tests, but let's see
    print(len(unique_nums)) # 3
    
    # 6. Dict comprehension
    mapping: dict[int, int] = {x: x * 10 for x in nums if x < 4}
    print(mapping) # {1: 10, 2: 20, 3: 30}
    
    return 0

# Main function is called via CLI/codegen main wrapper
