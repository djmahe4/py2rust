import os

def test_external() -> None:
    cwd = os.getcwd()
    print(cwd)
    parent = os.path.dirname(cwd)
    print(parent)

test_external()
