def main() -> int:
    f = open("test.txt", "w")
    _ = f.write("Hello")
    f.close()
    return 0
