import asyncio
from agents import Agent, Runner, set_trace_processors
from langsmith.integrations.openai_agents_sdk import OpenAIAgentsTracingProcessor

from dotenv import load_dotenv
load_dotenv('.env.local')

async def main():
    agent = Agent(
        name="Captain Obvious",
        instructions="You are Captain Obvious, the world's most literal technical support agent of all time.",
    )

    question = "Why is my code failing when I try to divide by zero? I keep getting this error message."
    result = await Runner.run(agent, question)
    print(result.final_output)


if __name__ == "__main__":
    set_trace_processors([OpenAIAgentsTracingProcessor()])
    asyncio.run(main())