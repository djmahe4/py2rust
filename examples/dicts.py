def main() -> int:
    scores: dict[str, int] = {"alice": 90, "bob": 85}
    scores["charlie"] = 95
    alice_score: int = scores["alice"]
    print(alice_score)
    return 0
