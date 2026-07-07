from openai import OpenAI
from processor.config import cfg
from processor.llm.cache import LLMCache
from processor.log import get_logger

logger = get_logger(__name__)

class LLMClient:
    def __init__(self):
        cfg.validate_llm()
        self.client = OpenAI(base_url=cfg.api_url, api_key=cfg.api_key)
        self.cache = LLMCache()

    def ask(self, prompt: str) -> str:
        cached = self.cache.get(prompt)
        if cached is not None:
            logger.info("[CACHE HIT]")
            return cached
        logger.info("[LLM]")
        response = self.client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.choices[0].message.content or ""
        answer = self._clean_json(answer)
        self.cache.put(prompt, answer)
        return answer

    @staticmethod
    def _clean_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
            text = "\n".join(lines).strip()
        return text

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *args) -> None:
        self.cache.flush()
