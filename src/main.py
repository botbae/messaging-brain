import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass
class Agent:
    name: str

    def think(self, user_input: str) -> str:
        return f"[{self.name}] Plan: break the task into steps, then execute."

    def act(self, plan: str) -> str:
        return (
            f"[{self.name}] Output:\n"
            f"{plan}\n"
            "- Step 1: define goal\n"
            "- Step 2: plan steps\n"
            "- Step 3: execute\n"
            "- Step 4: review\n"
        )

def run():
    load_dotenv()
    mock_mode = os.getenv("MOCK_MODE", "true").lower() == "true"
    agent = Agent(name="LocalAgent")

    user_input = os.getenv("PROMPT", "Create next steps to build my agent project.")
    plan = agent.think(user_input)

    if mock_mode:
        return agent.act(plan)

    return "MOCK_MODE=false is set, but no API is wired yet."

if __name__ == "__main__":
    print(run())
