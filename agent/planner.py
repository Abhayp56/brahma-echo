import json
import re
import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


PLANNER_PROMPT = """You are the planning module of Brahma AI - Self-Improving Assistant.
Your job: break any user goal into a sequence of steps.

ABSOLUTE RULES:
- FOR ANY TASK OR ACTION ON THE USER'S PC (e.g. system control, apps, automation, data processing, scrapers, monitors, file management), ALWAYS USE tool: "generated_code" or a custom tool name.
- Ada-SI Forge Master will plan, write Python code, test in sandbox venv, and execute a dedicated Python skill on the fly.
- NEVER use legacy key-pressing or screen-observing tools.
- NEVER reference previous step results in parameters. Every step is independent.
- Max 5 steps. Use the minimum steps needed.

AVAILABLE CORE TOOLS:

generated_code
  description: string (required) — natural language explanation of the desktop task to forge & execute

web_search
  query: string (required) — write a clear, focused search query

EXAMPLES:

Goal: "scan top RAM consuming processes"
Steps:
generated_code | description: "Scan system processes and list top RAM consuming processes"

Goal: "What is the price of Bitcoin"
Steps:
web_search | query: "Bitcoin price today USD"

OUTPUT — return ONLY valid JSON, no markdown, no explanation, no code blocks:
{
  "goal": "...",
  "steps": [
    {
      "step": 1,
      "tool": "tool_name",
      "description": "what this step does",
      "parameters": {},
      "critical": true
    }
  ]
}
"""


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _looks_like_website_goal(goal: str) -> bool:
    text = (goal or "").lower()
    return any(token in text for token in (
        "website",
        "landing page",
        "landingpage",
        "portfolio",
        "business site",
        "product site",
        "marketing site",
        "homepage",
        "web page",
        "site for",
        "build a site",
        "create a site",
        "create a website",
    ))


def _rewrite_generated_step(step: dict, goal: str) -> None:
    if step.get("tool") != "generated_code":
        return
    desc = step.get("description", goal) or goal
    if _looks_like_website_goal(goal):
        print(f"[Planner] 🌐 Website goal detected — routing to claude_code")
        step["tool"] = "claude_code"
        step["parameters"] = {
          "description": desc[:1200],
        }
        return
    print(f"[Planner] ⚡ Un-coded task detected — routing to Ada-SI Forge Master")
    step["parameters"] = {"description": desc[:1200], "prompt": goal}


def create_plan(goal: str, context: str = "") -> dict:
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    
    # Dynamically inject Ada-SI custom tools if available
    effective_prompt = PLANNER_PROMPT
    try:
        from core.ada_si_bridge import ada_bridge
        custom_tools = ada_bridge.list_installed_custom_tools()
        if custom_tools:
            extra_tools_text = "\n\nCUSTOM FORGED TOOLS AVAILABLE:\n"
            for ct in custom_tools:
                name = ct.get("name", ct.get("tool_name", "unknown"))
                desc = ct.get("description", "Forged custom tool")
                extra_tools_text += f"- {name}: {desc}\n"
            effective_prompt += extra_tools_text
    except Exception as exc:
        pass

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction=effective_prompt
    )

    user_input = f"Goal: {goal}"
    if context:
        user_input += f"\n\nContext: {context}"

    try:
        response = model.generate_content(user_input)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        plan = json.loads(text)

        if "steps" not in plan or not isinstance(plan["steps"], list):
            raise ValueError("Invalid plan structure")

        for step in plan["steps"]:
            _rewrite_generated_step(step, goal)

        print(f"[Planner] ✅ Plan: {len(plan['steps'])} steps")
        for s in plan["steps"]:
            print(f"  Step {s['step']}: [{s['tool']}] {s['description']}")

        return plan

    except json.JSONDecodeError as e:
        print(f"[Planner] ⚠️ JSON parse failed: {e}")
        return _fallback_plan(goal)
    except Exception as e:
        print(f"[Planner] ⚠️ Planning failed: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    print("[Planner] 🔄 Fallback plan")
    if _looks_like_website_goal(goal):
        return {
          "goal": goal,
          "steps": [
            {
              "step": 1,
              "tool": "claude_code",
              "description": f"Create the requested website with Claude Code: {goal}",
              "parameters": {"description": goal},
              "critical": True,
            }
          ],
        }
    return {
        "goal": goal,
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": f"Search for: {goal}",
                "parameters": {"query": goal},
                "critical": True
            }
        ]
    }


def replan(goal: str, completed_steps: list, failed_step: dict, error: str) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=PLANNER_PROMPT
    )

    completed_summary = "\n".join(
        f"  - Step {s['step']} ({s['tool']}): DONE" for s in completed_steps
    )

    prompt = f"""Goal: {goal}

Already completed:
{completed_summary if completed_summary else '  (none)'}

Failed step: [{failed_step.get('tool')}] {failed_step.get('description')}
Error: {error}

Create a REVISED plan for the remaining work only. Do not repeat completed steps."""

    try:
        response = model.generate_content(prompt)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        plan     = json.loads(text)

        for step in plan.get("steps", []):
            _rewrite_generated_step(step, goal)

        print(f"[Planner] 🔄 Revised plan: {len(plan['steps'])} steps")
        return plan
    except Exception as e:
        print(f"[Planner] ⚠️ Replan failed: {e}")
        return _fallback_plan(goal)
