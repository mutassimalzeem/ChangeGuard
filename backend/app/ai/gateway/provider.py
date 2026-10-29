"""The sole provider SDK boundary. SDK retries are disabled; the gateway owns them."""

from copy import deepcopy

from app.ai.gateway.types import GatewayUnavailableError, ProviderCallError, ProviderResponse, Usage


def strict_schema(schema):
    """Convert the generated Pydantic object schema to the provider's strict subset."""
    schema = deepcopy(schema)

    def visit(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)
    return schema


class OpenAIProvider:
    def __init__(self, settings, *, client=None):
        self.settings, self._client = settings, client

    def client(self):
        if self._client is None:
            if self.settings.llm_provider != "openai" or not self.settings.llm_api_key:
                raise GatewayUnavailableError("Configure the model provider")
            from openai import OpenAI

            return OpenAI(api_key=self.settings.llm_api_key, max_retries=0)
        return self._client

    def _invoke(self, operation, **kwargs):
        from openai import APIConnectionError, APIStatusError

        client = self.client()
        try:
            if operation == "generate":
                return client.chat.completions.create(**kwargs)
            return client.embeddings.create(**kwargs)
        except APIConnectionError:
            raise ProviderCallError(retryable=True) from None
        except APIStatusError as exc:
            raise ProviderCallError(
                retryable=exc.status_code in {408, 409, 429} or exc.status_code >= 500
            ) from None
        finally:
            # Injected clients belong to the caller. Each internally created SDK
            # client is closed even when an attempt fails or a task falls back.
            if self._client is None:
                client.close()

    def generate(self, *, policy, messages, schema):
        kwargs = {
            "model": policy.model,
            "temperature": policy.temperature,
            "max_completion_tokens": policy.max_tokens,
            "timeout": policy.timeout,
            "messages": messages,
        }
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "gateway_output",
                    "strict": True,
                    "schema": strict_schema(schema),
                },
            }
        result = self._invoke("generate", **kwargs)
        choice = result.choices[0]
        usage = (
            Usage(result.usage.prompt_tokens, result.usage.completion_tokens)
            if result.usage
            else Usage()
        )
        return ProviderResponse(
            content=choice.message.content or "",
            usage=usage,
            finish_reason=choice.finish_reason,
            refused=bool(choice.message.refusal),
        )

    def embed(self, *, policy, texts):
        result = self._invoke(
            "embed", model=policy.model, input=texts, dimensions=1536, timeout=policy.timeout
        )
        if sorted(row.index for row in result.data) != list(range(len(texts))):
            raise ProviderCallError() from None
        return ProviderResponse(
            vectors=[row.embedding for row in sorted(result.data, key=lambda row: row.index)],
            usage=Usage(result.usage.prompt_tokens, 0) if result.usage else Usage(),
        )
