import requests
from typing import Optional

class OllamaClient:
    def __init__(self, model: str = "deepseek-coder", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    def generate(self, prompt: str, timeout: int = 30) -> str:
        try:
            url = f"{self.host}/api/generate"
            payload = {"model": self.model, "prompt": prompt, "stream": False}
            res = requests.post(url, json=payload, timeout=timeout)
            if res.status_code == 200:
                return res.json().get("response", "")
            return f"FAIL: status code {res.status_code}"
        except Exception as e:
            return f"FAIL: {str(e)}"
