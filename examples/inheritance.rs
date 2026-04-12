use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write, Seek, SeekFrom};

struct Animal {
    name: String,
}

impl Animal {
    fn speak(&self) -> i32 {
        return 0;
    }
    fn new(&self, name: String) -> Self {
        return Self { name: name };
    }
}

struct Dog {
}

impl Dog {
    fn speak(&self) -> i32 {
        return 42;
    }
    fn new(&self, name: String) -> Self {
        return Self { name: name };
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
    let d = Dog::new("Buddy".to_string());
    let result = d.speak();
    println!("{}", result);
    return 0;
}
