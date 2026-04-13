class A:
    def greet(self) -> str:
        return "A"

class B(A):
    def greet(self) -> str:
        return "B"
    
    def specific_b(self) -> str:
        return "Specific B"

class C(A):
    def greet(self) -> str:
        return "C"
    
    def specific_c(self) -> str:
        return "Specific C"

class D(B, C):
    def greet(self) -> str:
        return "D"

def main() -> int:
    d: D = D()
    print(d.greet())
    print(d.specific_b())
    print(d.specific_c())
    return 0
