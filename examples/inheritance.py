class Animal:
    name: str = ""

    def __init__(self, name: str) -> None:
        self.name = name

    def speak(self) -> int:
        return 0


class Dog(Animal):
    def __init__(self, name: str) -> None:
        self.name = name

    def speak(self) -> int:
        return 42


def main() -> int:
    d: Dog = Dog("Buddy")
    result: int = d.speak()
    print(result)
    return 0
