"""
Tessera MCP Server

Exposes the Tessera Terminal as MCP-compatible tools that any AI agent can call.

Tools provided:
  tessera_connect       - Connect to the terminal with an agent profile
  tessera_get_screen    - View the current screen (data + available actions)
  tessera_execute       - Execute an action on the terminal
  tessera_audit_log     - View the session audit log
  tessera_disconnect    - End the session

This can run as a standalone FastAPI server that agents connect to,
or be integrated into an MCP host.
"""
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from tessera.contract.schema import TesseraContract, AgentProfile, AgentTrust, AgentCapabilities
from tessera.terminal.engine import TesseraTerminal


# ── Request Models ──

class ConnectRequest(BaseModel):
    provider: str
    agent_name: str
    trust_level: str = "identified"   # anonymous, identified, verified, super_agent
    purpose: str = "general"
    operator: Optional[str] = None
    can_transact: bool = False
    max_transaction_amount: Optional[float] = None
    max_daily_spend: Optional[float] = None
    delegated_by_user: bool = False


class ExecuteRequest(BaseModel):
    session_id: str
    action_id: str
    params: dict = {}
    confirmed: bool = False


class ScreenRequest(BaseModel):
    session_id: str


class AuditRequest(BaseModel):
    session_id: str


class DisconnectRequest(BaseModel):
    session_id: str


# ── MCP Server App ──

def create_mcp_server(contract_path: str, site_url: str) -> FastAPI:
    """Create a FastAPI MCP server for a Tessera terminal."""

    # Load contract
    with open(contract_path) as f:
        contract_data = json.load(f)
    contract = TesseraContract(**contract_data)

    # Create terminal
    terminal = TesseraTerminal(contract, site_url)

    app = FastAPI(
        title=f"Tessera MCP Server — {contract.site_name}",
        description=f"MCP tools for AI agents to interact with {contract.site_name} "
                    "through the Tessera terminal.",
        version="0.1.0",
    )

    # ── Tool: Connect ──

    @app.post("/tools/tessera_connect")
    def tessera_connect(req: ConnectRequest):
        """
        Connect to the Tessera terminal with an agent profile.
        Returns session ID and resolved permissions.
        """
        agent = AgentProfile(
            provider=req.provider,
            agent_name=req.agent_name,
            trust_level=AgentTrust(req.trust_level),
            purpose=req.purpose,
            operator=req.operator,
            capabilities=AgentCapabilities(
                can_transact=req.can_transact,
                max_transaction_amount=req.max_transaction_amount,
                max_daily_spend=req.max_daily_spend,
            ),
            delegated_by_user=req.delegated_by_user,
        )
        result = terminal.connect(agent)
        if result["status"] == "denied":
            raise HTTPException(status_code=403, detail=result["reason"])
        return result

    # ── Tool: Get Screen ──

    @app.post("/tools/tessera_get_screen")
    def tessera_get_screen(req: ScreenRequest):
        """
        View the current screen. Returns visible data and available actions.
        This is how the agent "sees" the website.
        """
        try:
            return terminal.get_screen(req.session_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Tool: Execute Action ──

    @app.post("/tools/tessera_execute")
    def tessera_execute(req: ExecuteRequest):
        """
        Execute an action on the terminal.
        The action must be available on the current screen and
        within the agent's permissions.
        """
        try:
            return terminal.execute_action(
                req.session_id, req.action_id, req.params, req.confirmed
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Tool: Audit Log ──

    @app.post("/tools/tessera_audit_log")
    def tessera_audit_log(req: AuditRequest):
        """View the full audit log for this session."""
        try:
            return {"audit_log": terminal.get_audit_log(req.session_id)}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Tool: Disconnect ──

    @app.post("/tools/tessera_disconnect")
    def tessera_disconnect(req: DisconnectRequest):
        """End the session and get the final audit log."""
        try:
            return terminal.disconnect(req.session_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Info Endpoint ──

    @app.get("/")
    def info():
        """Terminal info with full flow map."""
        flow_map = []
        for screen in contract.screens:
            screen_info = {
                "id": screen.id,
                "name": screen.name,
                "description": screen.description,
                "actions": [],
            }
            for action in screen.actions:
                action_info = {
                    "id": action.id,
                    "name": action.name,
                    "description": action.description,
                    "transitions_to": action.transitions_to,
                    "parameters": [p.name for p in action.parameters],
                }
                screen_info["actions"].append(action_info)
            flow_map.append(screen_info)

        return {
            "tessera_terminal": contract.site_name,
            "contract_id": contract.contract_id,
            "tier": contract.tier.value,
            "entry_screen": contract.entry_screen,
            "screens": [s.id for s in contract.screens],
            "flow_map": flow_map,
            "tools": [
                {"name": "tessera_connect", "description": "Connect with agent profile"},
                {"name": "tessera_get_screen", "description": "View current screen"},
                {"name": "tessera_execute", "description": "Execute an action"},
                {"name": "tessera_audit_log", "description": "View audit log"},
                {"name": "tessera_disconnect", "description": "End session"},
            ],
        }

    return app


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="Tessera MCP Server")
    parser.add_argument("--contract", default="../../simulations/shopping/contract.json",
                        help="Path to contract JSON")
    parser.add_argument("--site-url", default="http://localhost:8000",
                        help="URL of the actual website")
    parser.add_argument("--port", type=int, default=8001,
                        help="Port for the MCP server")
    args = parser.parse_args()

    contract_path = str(Path(args.contract).resolve())
    print(f"Starting Tessera MCP Server")
    print(f"  Contract: {contract_path}")
    print(f"  Site URL: {args.site_url}")
    print(f"  MCP Port: {args.port}")
    print(f"  Docs: http://localhost:{args.port}/docs")

    app = create_mcp_server(contract_path, args.site_url)
    uvicorn.run(app, host="0.0.0.0", port=args.port)
