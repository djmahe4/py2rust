# Semantic Validation Schema

This schema documents the record structure stored in the JSON Lines format inside the validation store (`.py2rust/validations.jsonl`).

## Fields

| Key | Type | Description |
|---|---|---|
| `timestamp` | `string` | The ISO-8601 UTC timestamp when the validation was recorded. |
| `symbol_name` | `string` | The name of the Python function/method/class analyzed. |
| `python_source` | `string` | The original Python source code snippet. |
| `generated_rust` | `string` | The translated Rust source code snippet. |
| `verdict` | `string` | `PASS` or `FAIL` indicating behavioral equivalence status. |
| `confidence` | `float` | Equivalence confidence rating between `0.0` and `1.0`. |
| `reasoning` | `string` | Detailed analysis explanation provided by the LLM. |
| `suggested_fix` | `string` | Optional fix suggestion or compilation adjustment code/description if the verdict is `FAIL`. |

## Example Record

```json
{
  "timestamp": "2026-05-23T16:41:30.123456+00:00",
  "symbol_name": "calc_sum",
  "python_source": "def calc_sum(a, b): return a + b",
  "generated_rust": "fn calc_sum(a: i32, b: i32) -> i32 { a + b }",
  "verdict": "PASS",
  "confidence": 0.98,
  "reasoning": "Behaviorally identical.",
  "suggested_fix": ""
}
```
