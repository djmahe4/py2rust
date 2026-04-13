use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write, Seek, SeekFrom};

struct FileHandle {
    file: File,
}

impl FileHandle {
    fn open(path: &str, mode: &str) -> std::io::Result<Self> {
        let file = match mode {
            "r" => File::open(path)?,
            "w" => {
                let f = File::create(path)?;
                f
            },
            "a" => {
                let f = OpenOptions::new().append(true).open(path)?;
                f
            },
            "rb" => File::open(path)?,
            "wb" => File::create(path)?,
            "ab" => {
                let f = OpenOptions::new().append(true).open(path)?;
                f
            },
            _ => File::open(path)?,
        };
        Ok(FileHandle { file })
    }

    fn read(&mut self) -> std::io::Result<String> {
        let mut contents = String::new();
        self.file.read_to_string(&mut contents)?;
        Ok(contents)
    }

    fn readline(&mut self) -> std::io::Result<String> {
        let mut reader = BufReader::new(&self.file);
        let mut line = String::new();
        reader.read_line(&mut line)?;
        Ok(line)
    }

    fn write(&mut self, content: &str) -> std::io::Result<()> {
        self.file.write_all(content.as_bytes())
    }

    fn close(self) -> std::io::Result<()> {
        Ok(())
    }

    fn tell(&mut self) -> std::io::Result<u64> {
        self.file.stream_position()
    }

    fn seek(&mut self, pos: u64) -> std::io::Result<u64> {
        self.file.seek(SeekFrom::Start(pos))
    }
}

fn add(x: i32, y: i32) -> i32 {
    return x + y;
}

fn multiply(x: i32, y: i32) -> i32 {
    return x * y;
}

fn main() -> () {
    let mut a: i32 = 0;
    let mut b: i32 = 0;
    let sum_result: i32 = 0;
    let product: i32 = 0;

    a = 10;
    b = 5;
    sum_result = add(a, b);
    product = multiply(a, b);
    println!("{}", sum_result);
    println!("{}", product);
    return;
}
