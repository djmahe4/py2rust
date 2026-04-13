def divide(a: int, b: int) -> int:
    if b == 0:
        raise ValueError("Division by zero")
    return a // b

def main() -> int:
    try:
        x = divide(10, 0)
        print(x)
    except ValueError:
        print(-1)
    
    try:
        y = divide(10, 2)
        print(y)
    except ValueError:
        print(-2)
    return 0
