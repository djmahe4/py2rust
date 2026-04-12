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

    fn tell(&self) -> std::io::Result<u64> {
        self.file.stream_position()
    }

    fn seek(&mut self, pos: u64) -> std::io::Result<u64> {
        self.file.seek(SeekFrom::Start(pos))
    }
}

fn sum_list(nums: Vec<i32>) -> i32 {
    let mut n: i32 = 0;

    let mut total = 0;
    for n in 0..nums.len() as i32 {
        total = total + ({ let __coll = &(nums); let __idx_raw = n; let actual_idx = if __idx_raw < 0 { (__idx_raw + (__coll.len() as i32) as i32) as usize } else { __idx_raw as usize }; __coll[actual_idx] });
    }
    return total;
}

fn main() -> i32 {
    let numbers = vec![1, 2, 3, 4, 5];
    let result = sum_list(numbers);
    println!("{}", result);
    return 0;
}
