def foo() -> None:
    print("foo")

if __name__ == "__main__":
    foo()
    print("This should be skipped")

print("This should also be skipped because it follows main block")
