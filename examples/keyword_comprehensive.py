import math as m

def test_print_variants() -> None:
    a = 1
    b = 2.5
    c = "hello"
    # Multi-variable print
    print(a, b, c)
    # Print with sep and end
    print(a, b, sep="|", end="!!!\n")
    # Print empty
    print()

def test_import_alias() -> None:
    # Using the alias m for math
    # In mock mode, this should work
    res = m.sqrt(16)
    print("sqrt(16) =", res)

def test_keywords_combinations() -> None:
    global x
    x = 10
    assert x == 10, "x should be 10"
    
    with open("test_keywords.txt", "w") as f:
        f.write("test")
    
    # Nested with
    with open("test_keywords.txt", "r") as f1:
        with open("test_keywords_copy.txt", "w") as f2:
            content = f1.read()
            f2.write(content)

if __name__ == "__main__":
    test_print_variants()
    test_import_alias()
    test_keywords_combinations()
