from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]


class VeteranAccessAgent:
    def __init__(
        self,
        *,
        system_prompt_version: str = "v3",
        project_name: str = "veteran-access-mcp-eval",
        phoenix_endpoint: str = "http://localhost:6006",
    ) -> None:
        self.system_prompt_version = system_prompt_version
        self.project_name = project_name
        self.phoenix_endpoint = phoenix_endpoint
        self.client = None
        self.agent = None

    def _load_system_prompt(self) -> str:
        path = (
            Path(__file__).parent
            / "prompts"
            / f"system_prompt_{self.system_prompt_version}.txt"
        )
        return path.read_text(encoding="utf-8")

    def _collector_endpoint(self) -> str:
        return self.phoenix_endpoint.rstrip("/") + "/v1/traces"

    async def initialize(self) -> None:
        tracer_provider = register(
            project_name=self.project_name,
            endpoint=self._collector_endpoint(),
        )
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

        self.client = MultiServerMCPClient(
            {
                "veteran_access_mcp": {
                    "transport": "stdio",
                    "command": "uv",
                    "args": ["run", "veteran-access-mcp"],
                    "cwd": str(REPO_ROOT),
                }
            }
        )
        tools = await self.client.get_tools()

        api_key = os.environ["USAI_API_KEY"]
        base_url = os.environ["USAI_BASE_URL"].rstrip("/") + "/api/v1"
        model = ChatOpenAI(
            model=os.getenv("AGENT_MODEL", "gpt-5.6"),
            api_key=api_key,
            base_url=base_url,
            temperature=0,
        )
        self.agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=self._load_system_prompt(),
        )

    async def run(self, query: str) -> str:
        if self.agent is None:
            await self.initialize()
        result = await self.agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]}
        )
        messages = result["messages"]
        return str(messages[-1].content)

    def create_experiment_task(self):
        config = {
            "system_prompt_version": self.system_prompt_version,
            "project_name": self.project_name,
            "phoenix_endpoint": self.phoenix_endpoint,
        }

        def task(example):
            # Each Phoenix task invocation gets a fresh agent, MCP client, and
            # async model client. This keeps loop-bound resources inside the
            # same asyncio.run() lifecycle instead of caching them across rows.
            agent = VeteranAccessAgent(**config)
            return asyncio.run(agent.run(example.input["query"]))

        return task


async def _smoke() -> None:
    agent = VeteranAccessAgent()
    print(
        await agent.run(
            "For DEMO-CARD-5000335-001, show the current scheduling encounter and access-standard status."
        )
    )


if __name__ == "__main__":
    asyncio.run(_smoke())
