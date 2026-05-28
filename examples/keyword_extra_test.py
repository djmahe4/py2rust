# Testing more keywords: as, global, nonlocal

import math as m

def test_as() -> None:
    # m should be usable as as alias for math (ExternalObject in mock mode or if plugin exists)
    # Using it in a way that generates code
    print("math as m test")
    # In mock mode, m.pi might just be an ExternalObject
    # x = m.pi 

def test_global_local() -> None:
    # Testing that 'global' at least doesn't break the compiler
    global x
    x = 1
    print(x)

def main() -> None:
    test_as()
    test_global_local()

if __name__ == "__main__":
    main()
