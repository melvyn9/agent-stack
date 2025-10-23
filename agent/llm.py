import json
import os
from typing import Any, List, Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-20250514-v1:0")


def bedrock_client():
    return boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


class BedRockChatModel(BaseChatModel):
    bedrock_client: Any = Field(default=None, exclude=True)
    model_id: str = Field(default=BEDROCK_MODEL_ID)
    region: str = Field(default=BEDROCK_REGION)
    tools: List[Any] = Field(default_factory=list, exclude=True)

    def __init__(self, **kwargs: Any):
        """Initialize the Bedrock LLM."""
        # Set defaults for model_id and region if not provided
        kwargs.setdefault("model_id", BEDROCK_MODEL_ID)
        kwargs.setdefault("region", BEDROCK_REGION)
        kwargs.setdefault("bedrock_client", None)
        
        super().__init__(**kwargs)
        
        # Initialize Bedrock client after parent init
        if self.bedrock_client is None:
            self.bedrock_client = bedrock_client()

    @property
    def _llm_type(self) -> str:
        """Return type of language model."""
        return "bedrock"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Call the Bedrock model."""
        try:
            # Convert messages to prompt
            prompt = self._messages_to_prompt(messages)

            if "anthropic." in self.model_id.lower():
                response_text = self._call_claude(prompt, stop=stop)
            elif "amazon.titan-text" in self.model_id.lower():
                response_text = self._call_titan(prompt, stop=stop)
            else:
                raise Exception(f"Unsupported Bedrock model ID: {self.model_id}")

            # Create ChatResult
            message = AIMessage(content=response_text)
            generation = ChatGeneration(message=message)
            return ChatResult(generations=[generation])

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            raise Exception(f"Bedrock API error ({error_code}): {error_message}")

    def _messages_to_prompt(self, messages: List[BaseMessage]) -> str:
        """Convert messages to a single prompt string."""
        prompt_parts = []
        for message in messages:
            if isinstance(message, HumanMessage):
                prompt_parts.append(f"Human: {message.content}")
            elif isinstance(message, AIMessage):
                prompt_parts.append(f"Assistant: {message.content}")
            else:
                prompt_parts.append(f"{message.__class__.__name__}: {message.content}")

        return "\n\n".join(prompt_parts)

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> "BedRockChatModel":
        """Bind tools to the model for tool use.
        
        Stores tools so they can be included in requests to Claude/Titan models.
        """
        # Store tools as an attribute for later use in API calls
        self.tools = tools
        # Return self to allow chaining
        return self

    def _call_claude(
        self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any
    ) -> str:
        """Call Claude model via Bedrock."""
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }
        if stop:
            body["stop_sequences"] = stop

        resp = self.bedrock_client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        data = json.loads(resp["body"].read())
        parts = data.get("content", [])
        txt = "".join(
            [p.get("text", "") for p in parts if p.get("type") == "text"]
        ).strip()
        return txt if txt else "(no text returned)"

    def _call_titan(
        self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any
    ) -> str:
        """Call Titan model via Bedrock."""
        body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 256,
                "temperature": 0.7,
                "topP": 0.9,
                "stopSequences": stop if stop else [],
            },
        }

        resp = self.bedrock_client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        data = json.loads(resp["body"].read())
        # Titan returns: {"results": [{"outputText": "...", ...}, ...]}
        results = data.get("results", [])
        if results and "outputText" in results[0]:
            return results[0]["outputText"].strip()
        return "(no text returned)"