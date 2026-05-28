class Point:
    x: int = 0
    y: int = 0

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def get_x(self) -> int:
        return self.x

    def get_y(self) -> int:
        return self.y

    def distance_to(self, other_x: int) -> int:
        dx: int = self.x - other_x
        return dx


def main() -> int:
    p: Point = Point(3, 4)
    x: int = p.get_x()
    y: int = p.get_y()
    d: int = p.distance_to(0)
    return x + y + d
