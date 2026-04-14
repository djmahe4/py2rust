class Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, factor: int) -> "Point":
        return Point(self.x * factor, self.y * factor)

    def __eq__(self, other: "Point") -> bool:
        return self.x == other.x and self.y == other.y

    def __lt__(self, other: "Point") -> bool:
        if self.x != other.x:
            return self.x < other.x
        return self.y < other.y

    def __str__(self) -> str:
        return f"Point({self.x}, {self.y})"

def main() -> None:
    p1 = Point(10, 20)
    p2 = Point(5, 5)
    
    p3 = p1 + p2
    p4 = p1 - p2
    
    print(p3)
    print(p4)
    
    if p1 == p2:
        print("Equal")
    else:
        print("Not Equal")
    
    p5 = Point(10, 20)
    if p1 == p5:
        print("p1 == p5")

    if p2 < p1:
        print("p2 < p1")
    else:
        print("p2 >= p1")
    
    if p1 > p2:
        print("p1 > p2")

    p6 = p1 * 2
    print(p6)

    p7 = p1 + p2 # (15, 25)
    p8 = p7 - p2 # (10, 20)
    if p8 == p1:
        print("p8 == p1")

# if __name__ == "__main__":
#     main()
