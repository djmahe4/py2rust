fn add(x: i32, y: i32) -> i32 {
    return x + y;
}

fn multiply(x: i32, y: i32) -> i32 {
    return x * y;
}

fn main() -> i32 {
    let a: i32 = 10;
    let b: i32 = 5;
    let sum_result: i32 = add(a, b);
    let product: i32 = multiply(a, b);
    println!("{}", sum_result);
    println!("{}", product);
    return 0;
}
