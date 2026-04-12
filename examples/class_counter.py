class Counter:
    count: int = 0

    def __init__(self) -> None:
        self.count = 0

    def increment(self) -> None:
        self.count = self.count + 1

    def get_count(self) -> int:
        return self.count


def main() -> int:
    c: Counter = Counter()
    c.increment()
    c.increment()
    c.increment()
    result: int = c.get_count()
    print(result)
    return 0
