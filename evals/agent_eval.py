"""
Tessera Phase 5b — LLM Agent Eval Runner

Runs actual LLM agents against simulation servers through the terminal.
Measures pass@1, steps-to-completion, invalid-action rate, and cost.

Architecture:
  1. Start simulation server (FastAPI on localhost)
  2. Create terminal from contract
  3. Connect agent
  4. Loop: show screen to LLM → LLM picks action → execute → repeat
  5. Check ground truth against simulation server state
  6. Collect metrics

Usage:
  python3 -m evals.agent_eval --task shopping-buy-cheapest --model qwen3:8b --trials 3
  python3 -m evals.agent_eval --suite all --model qwen3:8b --trials 5
  python3 -m evals.agent_eval --list  # show available tasks

Requires:
  - Ollama running locally (ollama serve)
  - pip install requests
"""
import json
import time
import uuid
import argparse
import subprocess
import sys
import os
import signal
import requests as http_requests
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path
from datetime import datetime, timezone

from tessera.contract.schema import (
    TesseraContract, AgentProfile, AgentTrust, AgentCapabilities,
)
from tessera.terminal.engine import TesseraTerminal


# ══════════════════════════════════════════════
# TASK DEFINITION
# ══════════════════════════════════════════════

@dataclass
class AgentTask:
    """A task for an LLM agent to complete."""
    id: str
    site: str                               # simulation name (e.g., "shopping")
    goal: str                               # natural language goal for the agent
    contract_path: str                      # path to contract JSON
    simulation_dir: str                     # path to simulation api/ directory
    simulation_port: int = 8100             # port for the simulation server
    max_steps: int = 15                     # max actions before giving up
    ground_truth: Optional[Callable] = None # function(sim_url) → bool
    setup: Optional[Callable] = None        # function(sim_url) to set up state before task
    category: str = "general"
    description: str = ""
    agent_purpose: str = "purchase"          # must match contract's allowed purposes


# ══════════════════════════════════════════════
# AGENT RESULT
# ══════════════════════════════════════════════

@dataclass
class AgentRun:
    """Result of one agent run."""
    task_id: str
    model: str
    trial: int
    passed: bool
    steps: int
    invalid_actions: int
    actions_taken: list[dict] = field(default_factory=list)
    ground_truth_passed: bool = False
    elapsed_seconds: float = 0.0
    error: str = ""
    final_screen: str = ""


@dataclass
class AgentTaskResult:
    """Aggregated result across trials for one task."""
    task_id: str
    model: str
    trials: int
    passed: int                     # pass@1 count
    pass_rate: float                # pass@1 rate
    avg_steps: float
    avg_invalid: float
    avg_elapsed: float
    runs: list[AgentRun] = field(default_factory=list)


# ══════════════════════════════════════════════
# OLLAMA CLIENT
# ══════════════════════════════════════════════

def check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        r = http_requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def list_ollama_models() -> list[str]:
    """List available Ollama models."""
    try:
        r = http_requests.get("http://localhost:11434/api/tags", timeout=3)
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def ollama_generate(model: str, prompt: str, system: str = "") -> str:
    """Call Ollama generate API and return the response text."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,      # low temperature for deterministic actions
            "num_predict": 512,      # cap output length
        },
    }
    if system:
        payload["system"] = system

    try:
        r = http_requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=120,
        )
        data = r.json()
        return data.get("response", "")
    except Exception as e:
        return f"ERROR: {e}"


# ══════════════════════════════════════════════
# SIMULATION SERVER MANAGEMENT
# ══════════════════════════════════════════════

def start_simulation(sim_dir: str, port: int) -> subprocess.Popen:
    """Start a simulation FastAPI server."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "warning"],
        cwd=sim_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )

    # Wait for server to be ready
    for _ in range(30):
        try:
            r = http_requests.get(f"http://localhost:{port}/", timeout=1)
            if r.status_code < 500:
                return proc
        except Exception:
            pass
        time.sleep(0.5)

    raise RuntimeError(f"Simulation at {sim_dir} failed to start on port {port}")


def stop_simulation(proc: subprocess.Popen):
    """Stop a simulation server."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ══════════════════════════════════════════════
# AGENT LOOP
# ══════════════════════════════════════════════

SYSTEM_PROMPT = """You are an AI agent navigating a website through a Tessera terminal.
You see screens with data and available actions. Your job is to complete the given task.

IMPORTANT RULES:
1. Respond with EXACTLY ONE action per turn, in this JSON format:
   {"action": "action_id", "params": {"key": "value"}}
2. If the task is complete, respond with:
   {"action": "DONE"}
3. Only use actions listed in "Available actions"
4. Read the screen data carefully before choosing an action

Do not explain your reasoning. Only output the JSON action."""


def run_agent(
    task: AgentTask,
    model: str,
    terminal: TesseraTerminal,
    sim_url: str,
    verbose_hint: bool = False,
) -> AgentRun:
    """Run one agent trial against a task."""
    start = time.monotonic()
    steps = 0
    invalid_actions = 0
    actions_taken = []

    # Connect — purpose comes from task config or defaults to 'purchase'
    agent_config = {
        "provider": "eval",
        "agent_name": f"eval-{model}",
        "trust_level": AgentTrust.VERIFIED,
        "purpose": task.agent_purpose if hasattr(task, 'agent_purpose') and task.agent_purpose else "purchase",
        "capabilities": AgentCapabilities(can_transact=True),
    }
    agent_profile = AgentProfile(**agent_config)
    connect_result = terminal.connect(agent_profile)
    if connect_result["status"] != "connected":
        error_msg = f"Connect failed: {connect_result.get('reason', connect_result)}"
        if verbose_hint:
            print(f"\n    ⚠ {error_msg}")
        return AgentRun(
            task_id=task.id, model=model, trial=0, passed=False,
            steps=0, invalid_actions=0, error=error_msg,
        )

    session_id = connect_result["session_id"]

    # Agent loop
    for step in range(task.max_steps):
        steps += 1

        # Get current screen
        screen = terminal.get_screen(session_id)
        screen_text = json.dumps(screen, indent=2, default=str)

        # Build prompt
        prompt = (
            f"TASK: {task.goal}\n\n"
            f"CURRENT SCREEN:\n{screen_text}\n\n"
            f"Step {step + 1}/{task.max_steps}. What action do you take?"
        )

        # Ask LLM
        response = ollama_generate(model, prompt, system=SYSTEM_PROMPT)

        # Parse LLM response
        action_data = _parse_agent_response(response)

        if action_data is None:
            invalid_actions += 1
            actions_taken.append({"step": step, "raw": response[:200], "parsed": None, "result": "parse_error"})
            continue

        if action_data.get("action") == "DONE":
            actions_taken.append({"step": step, "action": "DONE", "result": "agent_declared_done"})
            break

        action_id = action_data.get("action", "")
        params = action_data.get("params", {})

        # Execute action
        result = terminal.execute_action(session_id, action_id, params)
        status = result.get("status", "unknown")

        actions_taken.append({
            "step": step, "action": action_id, "params": params,
            "result": status, "detail": str(result)[:200],
        })

        if status == "denied":
            invalid_actions += 1

    elapsed = time.monotonic() - start

    # Check ground truth
    gt_passed = False
    if task.ground_truth:
        try:
            gt_passed = task.ground_truth(sim_url)
        except Exception as e:
            gt_passed = False

    # Disconnect
    try:
        terminal.disconnect(session_id)
    except Exception:
        pass

    return AgentRun(
        task_id=task.id, model=model, trial=0,
        passed=gt_passed, steps=steps, invalid_actions=invalid_actions,
        actions_taken=actions_taken, ground_truth_passed=gt_passed,
        elapsed_seconds=elapsed,
        final_screen=json.dumps(screen, default=str)[:500] if 'screen' in dir() else "",
    )


def _parse_agent_response(response: str) -> Optional[dict]:
    """Parse the LLM's action response. Handles various formats."""
    response = response.strip()

    # Try direct JSON parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code block
    if "```" in response:
        for block in response.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue

    # Try finding JSON object in the response
    start = response.find("{")
    end = response.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass

    return None


# ══════════════════════════════════════════════
# EVAL RUNNER
# ══════════════════════════════════════════════

def run_eval(
    task: AgentTask,
    model: str,
    trials: int = 3,
    verbose: bool = False,
) -> AgentTaskResult:
    """Run an agent eval: start server, run N trials, collect metrics."""

    # Start simulation
    if verbose:
        print(f"  Starting simulation: {task.simulation_dir}")

    sim_proc = None
    sim_url = f"http://localhost:{task.simulation_port}"

    try:
        sim_proc = start_simulation(task.simulation_dir, task.simulation_port)

        runs = []
        for trial in range(trials):
            if verbose:
                print(f"  Trial {trial + 1}/{trials}...", end=" ", flush=True)

            # Load contract and create fresh terminal per trial
            with open(task.contract_path) as f:
                contract_data = json.load(f)
            contract = TesseraContract(**contract_data)
            terminal = TesseraTerminal(contract, sim_url)

            # Run setup if provided
            if task.setup:
                task.setup(sim_url)

            # Run agent
            run = run_agent(task, model, terminal, sim_url, verbose_hint=verbose)
            run.trial = trial + 1
            runs.append(run)

            if verbose:
                icon = "✅" if run.passed else "❌"
                print(f"{icon} steps={run.steps} invalid={run.invalid_actions} "
                      f"time={run.elapsed_seconds:.1f}s")

    finally:
        if sim_proc:
            stop_simulation(sim_proc)

    # Aggregate
    passed = sum(1 for r in runs if r.passed)
    avg_steps = sum(r.steps for r in runs) / len(runs) if runs else 0
    avg_invalid = sum(r.invalid_actions for r in runs) / len(runs) if runs else 0
    avg_elapsed = sum(r.elapsed_seconds for r in runs) / len(runs) if runs else 0

    return AgentTaskResult(
        task_id=task.id, model=model, trials=trials,
        passed=passed, pass_rate=passed / trials if trials > 0 else 0,
        avg_steps=avg_steps, avg_invalid=avg_invalid, avg_elapsed=avg_elapsed,
        runs=runs,
    )


# ══════════════════════════════════════════════
# REPORTING
# ══════════════════════════════════════════════

def print_results(results: list[AgentTaskResult]):
    """Print a summary table."""
    print(f"\n{'='*75}")
    print(f"  TESSERA AGENT EVAL RESULTS")
    print(f"{'='*75}")
    print(f"  {'Task':<35} {'Model':<15} {'pass@1':>8} {'Steps':>7} {'Invalid':>8} {'Time':>7}")
    print(f"  {'-'*35} {'-'*15} {'-'*8} {'-'*7} {'-'*8} {'-'*7}")

    for r in results:
        rate = f"{r.passed}/{r.trials}"
        print(f"  {r.task_id:<35} {r.model:<15} {rate:>8} {r.avg_steps:>7.1f} "
              f"{r.avg_invalid:>8.1f} {r.avg_elapsed:>6.1f}s")

    print(f"{'='*75}")

    # Overall stats
    total_trials = sum(r.trials for r in results)
    total_passed = sum(r.passed for r in results)
    overall_rate = total_passed / total_trials if total_trials > 0 else 0
    print(f"  Overall: {total_passed}/{total_trials} ({overall_rate*100:.0f}%)")
    print()


def results_to_json(results: list[AgentTaskResult]) -> str:
    """Export results as JSON."""
    return json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": [
            {
                "task_id": r.task_id,
                "model": r.model,
                "trials": r.trials,
                "passed": r.passed,
                "pass_rate": r.pass_rate,
                "avg_steps": r.avg_steps,
                "avg_invalid": r.avg_invalid,
                "avg_elapsed": r.avg_elapsed,
                "runs": [
                    {
                        "trial": run.trial,
                        "passed": run.passed,
                        "steps": run.steps,
                        "invalid_actions": run.invalid_actions,
                        "elapsed_seconds": run.elapsed_seconds,
                        "actions": run.actions_taken,
                    }
                    for run in r.runs
                ],
            }
            for r in results
        ],
    }, indent=2)


# ══════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Tessera Agent Eval")
    parser.add_argument("--task", help="Task ID to run (or 'all')")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model name")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per task")
    parser.add_argument("--list", action="store_true", help="List available tasks")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--output", help="Save results JSON to file")
    args = parser.parse_args()

    # Import tasks
    from evals.tasks.agent_tasks import get_all_tasks, get_task

    if args.list:
        tasks = get_all_tasks()
        print(f"\nAvailable tasks ({len(tasks)}):")
        for t in tasks:
            print(f"  {t.id:<35} {t.description}")
        return

    if not check_ollama():
        print("ERROR: Ollama is not running. Start it with: ollama serve")
        sys.exit(1)

    models = list_ollama_models()
    if args.model not in [m.split(":")[0] + ":" + m.split(":")[-1] if ":" in m else m for m in models]:
        # Try partial match
        if not any(args.model in m for m in models):
            print(f"WARNING: Model '{args.model}' may not be available. Installed: {models}")

    if args.task == "all":
        tasks = get_all_tasks()
    else:
        task = get_task(args.task)
        if not task:
            print(f"ERROR: Unknown task '{args.task}'. Use --list to see available tasks.")
            sys.exit(1)
        tasks = [task]

    print(f"\nTessera Agent Eval")
    print(f"  Model: {args.model}")
    print(f"  Tasks: {len(tasks)}")
    print(f"  Trials: {args.trials}")
    print()

    results = []
    for task in tasks:
        print(f"[{task.id}] {task.description}")
        result = run_eval(task, args.model, args.trials, verbose=args.verbose)
        results.append(result)
        icon = "✅" if result.pass_rate > 0 else "❌"
        print(f"  {icon} pass@1: {result.passed}/{result.trials} "
              f"({result.pass_rate*100:.0f}%)")
        print()

    print_results(results)

    if args.output:
        with open(args.output, "w") as f:
            f.write(results_to_json(results))
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
