

T = TypeVar('T')

def first_element(items: List[T]) -> T:
    return items[0]

def main() -> None:
    nums = [1, 2, 3]
    strs = ["a", "b", "c"]
    print(first_element(nums))
    print(first_element(strs))
