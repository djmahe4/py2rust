"""
Test wave 20:
Tests for collections.deque, heapq (BinaryHeap), and Slice negative indexing.
"""

import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust

def _compile(src):
    return generate_rust(build_ir(parse(src)))

def test_deque_operations():
    src = """
from collections import deque

def test_deque() -> None:
    d = deque([1, 2, 3])
    d.append(4)
    d.appendleft(0)
    v1 = d.pop()
    v2 = d.popleft()
    d.extend([5, 6])
    d.extendleft([-1, -2])
"""
    code = _compile(src)
    assert "use std::collections::VecDeque;" in code
    assert "let mut d: VecDeque<i32> = VecDeque::from(vec![1, 2, 3]);" in code
    assert "d.push_back(4);" in code
    assert "d.push_front(0);" in code
    assert "let v1: i32 = d.pop_back().ok_or(PyError::IndexError(\"pop from an empty deque\".to_string()))?;" in code
    assert "let v2: i32 = d.pop_left().ok_or(PyError::IndexError(\"pop from an empty deque\".to_string()))?;" in code or "d.pop_front()" in code
    # Note: I implemented it as pop_front() in rust_codegen.py for popleft()
    assert "d.pop_front()" in code
    assert "d.extend(vec![5, 6]);" in code
    # extendleft in Python prepends elements one by one, so extendleft([A, B]) prepends A then B -> [B, A, ...]
    # My implementation used d.push_front(item) in a loop
    assert "for __item in vec![(-(1)), (-(2))] { d.push_front(__item); }" in code

def test_heapq_operations():
    src = """
import heapq

def test_heap() -> None:
    h = []
    heapq.heappush(h, 10)
    heapq.heappush(h, 5)
    heapq.heappush(h, 15)
    val = heapq.heappop(h)
    
    data = [3, 1, 4]
    heapq.heapify(data)
    
    # Peek
    top = h[0]
"""
    code = _compile(src)
    assert "use std::collections::BinaryHeap;" in code
    assert "use std::cmp::Reverse;" in code
    assert "let mut h: BinaryHeap<Reverse<i32>> = BinaryHeap::new();" in code
    assert "h.push(Reverse(10));" in code
    assert "h.push(Reverse(5));" in code
    assert "let val: i32 = h.pop().ok_or(PyError::IndexError(\"index out of range\".to_string()))?.0;" in code
    assert "let mut data: BinaryHeap<Reverse<i32>> = BinaryHeap::from(vec![3, 1, 4].into_iter().map(Reverse).collect::<Vec<_>>());" in code
    # Peek logic
    assert "h.peek().map(|r| r.0.clone()).ok_or(PyError::IndexError(\"heap index out of range\".to_string()))?" in code

def test_slice_negative_indices():
    src = """
def test_slice(l: list[int]) -> list[int]:
    return l[1:-1]

def test_str_slice(s: str) -> str:
    return s[:-2]
"""
    code = _compile(src)
    # List slice check
    assert "let __start = if 1 < 0 { 1 + __len } else { 1 };" in code
    assert "let __stop = if -(1) < 0 { -(1) + __len } else { -(1) };" in code
    assert "__coll[__start..__stop].to_vec()" in code
    
    # String slice check
    assert "__coll.chars().skip(__start).take(__stop - __start).collect::<String>()" in code
