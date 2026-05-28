class Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
    
    def __str__(self) -> str:
        return f"({self.x}, {self.y})"

def main() -> None:
    p = Point(1, 2)
    s = str(p)
    print(s)
    
    # Standard conversions
    num_str = "42"
    num = int(num_str)
    print(num)
