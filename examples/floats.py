def float_math(x: float, y: float) -> float:
    z: float = x + y
    a: float = x * 2.0
    b: float = y / 2.0
    return z + a - b

def main() -> int:
    res: float = float_math(10.5, 5.5)
    print(res)
    return 0
