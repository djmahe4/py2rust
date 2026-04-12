fn fib(n: i32) -> i32 {
    if n <= 1 {
        return n;
    }
    let a: i32 = 0;
    let b: i32 = 1;
    let i: i32 = 2;
    while i <= n {
        let temp: i32 = a + b;
        a = b;
        b = temp;
        i += 1;
    }
    return b;
}

fn main() -> i32 {
    let result: i32 = fib(10);
    println!("{}", result);
    return 0;
}
