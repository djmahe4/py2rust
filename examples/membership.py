def main() -> int:
    lst = [1, 2, 3]
    if 1 in lst:
        print(100)
    
    d = {"a": 10, "b": 20}
    if "a" in d:
        print(200)
    
    if "c" not in d:
        print(300)
    
    s = "hello"
    if "h" in s:
        print(400)
    return 0
