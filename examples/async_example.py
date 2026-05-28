async def say_hello(name: str) -> str:
    return "Hello, " + name

async def calculate(a: int, b: int) -> int:
    return a + b

async def main() -> None:
    msg = await say_hello("Async World")
    print(msg)
    
    val = await calculate(10, 20)
    print("Result:")
    print(val)
