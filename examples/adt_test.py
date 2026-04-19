# examples/adt_test.py
from typing import Optional, Union

def describe_number(x: Optional[int]) -> str:
    if x is None:
        return "Nothing"
    else:
        return f"Number: {x}"

def combine(x: Union[int, str]) -> str:
    if isinstance(x, int):
        return f"Int: {x}"
    elif isinstance(x, str):
        return f"Str: {x}"
    return "Unknown"

def main() -> None:
    print(describe_number(10))
    print(describe_number(None))
    
    print(combine(42))
    print(combine("hello"))

if __name__ == "__main__":
    main()
