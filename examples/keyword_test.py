# Testing Python keywords: with, assert

def test_assert() -> None:
    x = 10
    assert x > 0
    assert x == 10, "x should be 10"
    print("test_assert passed")

def test_with() -> None:
    # Note: open() in py2rust is often handled specially
    with open("test.txt", "w") as f:
        f.write("hello world")
    print("test_with passed")

def main() -> None:
    test_assert()
    test_with()

if __name__ == "__main__":
    main()
