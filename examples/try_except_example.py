def main() -> None:
    try:
        raise ValueError("inner err")
    except ValueError as e:
        try:
            raise Exception("outer err") from e
        except Exception as ex:
            print("caught nested")
    
    # testing early return from loop and try
    for i in range(5):
        try:
            if i == 3:
                break
            if i == 1:
                continue
            print(i)
        except Exception:
            _ = 0
            
    print(test_return())

def test_return() -> int:
    try:
        return 42
    except Exception:
        return -1

