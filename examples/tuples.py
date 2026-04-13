def swap(x: int, y: int) -> tuple[int, int]:
    return y, x

def main() -> int:
    a = 1
    b = 2
    a, b = swap(a, b)
    print(a)
    print(b)
    
    t = (10, 20)
    x, y = t
    print(x + y)
    return 0
