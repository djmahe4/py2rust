
class Container:
    items: list[int] = [0, 0, 0]
    
    def __init__(self) -> None:
        self.items = [0] * 3
        
    def __getitem__(self, idx: int) -> int:
        return self.items[idx]
        
    def __setitem__(self, idx: int, val: int) -> None:
        self.items[idx] = val

def test() -> None:
    c = Container()
    c[1] = 10
    print(c[1])

def main() -> None:
    test()

# if __name__ == "__main__":
#     main()
