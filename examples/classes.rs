use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write, Seek, SeekFrom};

struct Point {
    x: i32,
    y: i32,
}

impl Point {
    fn get_x(&self) -> i32 {
        return self.x;
    }
    fn get_y(&self) -> i32 {
        return self.y;
    }
    fn distance_to(&self, other_x: i32) -> i32 {
        let dx = self.x - other_x;
        return dx;
    }
    fn new(&self, x: i32, y: i32) -> Self {
        return Self { x: x, y: y };
    }
}

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

fn main() -> i32 {
    let p = Point::new(3, 4);
    let x = p.get_x();
    let y = p.get_y();
    let d = p.distance_to(0);
    return (x + y) + d;
}
