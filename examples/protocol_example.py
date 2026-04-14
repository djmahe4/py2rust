

class Drawable(Protocol):
    def draw(self) -> str:
        ...

class Circle:
    def __init__(self, radius: int) -> None:
        self.radius = radius
    def draw(self) -> str:
        return f"Circle({self.radius})"

class Square:
    def __init__(self, side: int) -> None:
        self.side = side
    def draw(self) -> str:
        return f"Square({self.side})"

def render(items: List[Drawable]) -> None:
    for item in items:
        print(item.draw())

def main() -> None:
    shapes = [Circle(5), Square(10)]
    render(shapes)
