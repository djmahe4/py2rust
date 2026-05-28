import json
import csv

def test_json() -> None:
    print("Testing JSON support...")
    data = {"a": 1, "b": [1, 2, 3], "c": {"d": True}}
    s = json.dumps(data)
    print("Serialized:", s)
    data2 = json.loads(s)
    print("Deserialized 'a':", data2["a"])
    print("Deserialized 'b':", data2["b"])
    
    # Test mutation if it's an ExternalObject
    data2["a"] = 42
    print("Updated 'a':", data2["a"])
    
    # Test iteration
    print("Iterating over keys:")
    for k in data2:
        print("Key:", k)

def test_csv() -> None:
    print("\nTesting CSV support...")
    # Create a temp csv file
    f1 = open("test.csv", "w")
    f1.write("name,age\nalice,30\nbob,25\n")
    f1.close()
    
    f2 = open("test.csv", "r")
    reader = csv.reader(f2)
    for row in reader:
        print("Row:", row)
    f2.close()

def test_attr() -> None:
    # Simulation of external object with attributes
    # In real scenarios, these would come from libraries like opencv/numpy
    # Here we just use a mock or assumes things are handled by ExternalObject
    pass

test_json()
test_csv()
test_attr()
