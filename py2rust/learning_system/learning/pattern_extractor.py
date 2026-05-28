import os
import re
from py2rust.learning_system.learning.pattern_store import PatternStore

class PatternExtractor:
    def __init__(self, pattern_store: PatternStore = None, evidence_threshold: int = 2, client=None):
        self.pattern_store = pattern_store or PatternStore()
        self.evidence_threshold = evidence_threshold
        self.client = client

    def extract_from_failures(self, failures: list[dict]):
        # Group failures by symbol name or a generalization key to see if they meet the threshold
        # For this implementation, we will treat failures as potential source code context.
        # If the number of failures is >= evidence_threshold, we trigger pattern learning.
        if len(failures) < self.evidence_threshold:
            return None
            
        # Form prompt presenting the failures and asking for generalization
        failures_summary = []
        for idx, f in enumerate(failures):
            failures_summary.append(f"""Failure {idx + 1}:
Symbol: {f.get('symbol_name')}
Python Source:
{f.get('python_source')}

Generated Rust:
{f.get('generated_rust')}

Failure Reasoning:
{f.get('reasoning')}
""")

        prompt = f"""TASK: Analyze the following compilation failures and extract a generalized translation adjustment pattern.

FAILURES:
{"\n".join(failures_summary)}

RESPOND ONLY WITH THE FOLLOWING SCHEMA:
PATTERN_ID: [snake_case identifier]
TRIGGER_PATTERN: [Python code/AST construct trigger]
TARGET_RUST: [Rust code snippet that is generated incorrectly]
REPLACEMENT_RUST: [Rust code snippet that is correct]
CONFIDENCE: [0.0 to 1.0]
"""

        response = self.client.generate(prompt) if self.client else "PATTERN_ID: default\nTRIGGER_PATTERN: default\nTARGET_RUST: default\nREPLACEMENT_RUST: default\nCONFIDENCE: 0.0"
        
        # Robust multi-line regex-based lookup using lookahead assertions
        def extract_field(field_name: str, default: str) -> str:
            pattern = re.compile(
                rf"{field_name}:\s*(.*?)(?=\s*(?:PATTERN_ID|TRIGGER_PATTERN|TARGET_RUST|REPLACEMENT_RUST|CONFIDENCE):|$)",
                re.IGNORECASE | re.DOTALL
            )
            match = pattern.search(response)
            if match:
                return match.group(1).strip()
            return default

        pattern_id = extract_field("PATTERN_ID", "unknown")
        trigger_pattern = extract_field("TRIGGER_PATTERN", "")
        target_rust = extract_field("TARGET_RUST", "")
        replacement_rust = extract_field("REPLACEMENT_RUST", "")
        
        confidence_str = extract_field("CONFIDENCE", "0.0")
        try:
            confidence = float(confidence_str)
        except ValueError:
            confidence = 0.0
                    
        new_pattern = {
            "pattern_id": pattern_id,
            "trigger_pattern": trigger_pattern,
            "target_rust": target_rust,
            "replacement_rust": replacement_rust,
            "evidence_count": len(failures),
            "confidence": confidence
        }
        
        self.pattern_store.save_pattern(new_pattern)
        return new_pattern
