from app.providers.base import ChatMessage


class MockProvider:
    async def generate(self, messages: list[ChatMessage]) -> str:
        topic = "the requested topic"
        for message in reversed(messages):
            if "Topic:" in message.content:
                topic = message.content.split("Topic:", 1)[1].splitlines()[0].strip()
                break

        return (
            f"Executive Summary\n"
            f"{topic} is being monitored through the AI News Agent pipeline.\n\n"
            f"Key Points\n"
            f"- The first implementation normalizes source material before generation.\n"
            f"- The writer and critic agents are separated to improve answer quality.\n"
            f"- Citations should be attached whenever external sources are available.\n\n"
            f"Analysis\n"
            f"This mock provider confirms that the API pipeline is reachable without "
            f"requiring a local Ollama model."
        )
