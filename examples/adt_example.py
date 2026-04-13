
class Color(Enum):
    RED = 1
    GREEN = 2
    BLUE = 3

def describe_color(c: Color) -> None:
    match c:
        case Color.RED:
            print("It is red")
        case Color.GREEN:
            print("It is green")
        case Color.BLUE:
            print("It is blue")
        case _:
            print("Unknown color")

def check_value(x: int) -> None:
    match x:
        case 1:
            print("One")
        case 2:
            print("Two")
        case y:
            print("Other value")

def main() -> None:
    describe_color(Color.RED)
    describe_color(Color.GREEN)
    check_value(1)
    check_value(2)
    check_value(3)
