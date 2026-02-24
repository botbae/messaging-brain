from dataclasses import dataclass

@dataclass
class Agent:
    name: str

    def think(self, user_input: str) -> str:
        return f"[{self.name}] Plan: break the task into steps, then execute."

    def act(self, plan: str) -> str:
        return f"[{self.name}] Output: {plan}\n- Step 1: make project structure\n- Step 2: add config\n- Step 3: add real LLM later"

if __name__ == "__main__":
    a = Agent(name="LocalAgent")
    user_input = "Create next steps to build my agent project."
    plan = a.think(user_input)
    print(a.act(plan))
