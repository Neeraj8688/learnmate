class NoProvider:
    configured = False

    def generate(self, prompt: str) -> str:
        raise RuntimeError("LLM not configured")
