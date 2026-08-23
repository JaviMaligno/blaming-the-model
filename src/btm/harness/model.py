"""El modelo real que usa el sistema entregado, y el guard de temperatura.

El guard vive aquí, en el arnés, y no en `btm.system.model`: un guard visible
dentro del paquete que se le entrega al agente contestaría por adelantado la
pregunta que la métrica del interruptor quiere hacer.
"""

import os


class AzureModel:
    def __init__(self, *, deployment: str | None = None, temperature: float | None = None) -> None:
        if temperature is not None:
            raise ValueError("este despliegue no admite temperature")
        self.deployment = deployment or os.environ.get("BTM_DEPLOYMENT", "")

    @property
    def supports_temperature(self) -> bool:
        return False

    def complete(self, messages: list[dict]) -> str:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=os.environ["BTM_AZURE_ENDPOINT"],
            api_key=os.environ["BTM_AZURE_KEY"],
            api_version=os.environ.get("BTM_API_VERSION", "2026-01-01"),
        )
        response = client.chat.completions.create(model=self.deployment, messages=messages)
        return response.choices[0].message.content or ""
