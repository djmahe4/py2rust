def get_point() -> tuple[int, int]:
    return (10, 20)

def main() -> int:
    x: int = 0
    y: int = 0
    x, y = get_point()
    print(x)
    print(y)
    
    a: int = 30
    b: int = 40
    a, b = (50, 60)
    print(a)
    print(b)
    return 0
