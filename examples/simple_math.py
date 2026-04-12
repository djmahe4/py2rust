def add(x: int, y: int) -> int:
    return x + y

def multiply(x: int, y: int) -> int:
    return x * y

def main() -> int:
    a: int = 10
    b: int = 5
    sum_result: int = add(a, b)
    product: int = multiply(a, b)
    print(sum_result)
    print(product)
    return 0
