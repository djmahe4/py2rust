#[derive(Debug)]
pub enum PyError {
    Exception(String),
}

pub enum TryResult<T> {
    Normal,
    Return(T),
    Break,
    Continue,
}

fn divide(a: i32, b: i32) -> Result<i32, PyError> {
    if b == 0 { Err(PyError::Exception("div zero".to_string())) }
    else { Ok(a / b) }
}

fn test_func() -> Result<i32, PyError> {
    let mut sum = 0;
    for i in 0..3 {
        let __res = (|| -> Result<TryResult<i32>, PyError> {
            let v = divide(10, i)?;
            if v == 5 {
                return Ok(TryResult::Break);
            }
            sum += v;
            Ok(TryResult::Normal)
        })();
        
        match __res {
            Ok(TryResult::Return(v)) => return Ok(v),
            Ok(TryResult::Break) => break,
            Ok(TryResult::Continue) => continue,
            Ok(TryResult::Normal) => {},
            Err(e) => {
                println!("Caught: {:?}", e);
            }
        }
    }
    Ok(sum)
}

fn main() {
    println!("{:?}", test_func());
}
