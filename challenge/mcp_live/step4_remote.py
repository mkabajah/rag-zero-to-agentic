"""
MCP LIVE · STEP 4 · the same server, REMOTE: Streamable HTTP + a bearer token.

LOCAL or REMOTE?
  stdio (steps 1–3)       The client STARTS your server as a child process on the same machine and
                          talks over stdin/stdout. No network port, so no auth needed: only you can
                          run it. Claude Code, Claude Desktop and Kiro all do this.
  Streamable HTTP (here)  Your server runs on its own and LISTENS on a URL (http://host:8000/mcp).
                          Many clients can share it, but anyone who reaches the URL can call it,
                          so it needs auth. (The older SSE transport is deprecated.)

Run it on your laptop:
    export MCP_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
    python challenge/mcp_live/step4_remote.py                     # → http://127.0.0.1:8000/mcp

    claude mcp add --transport http cv-remote http://127.0.0.1:8000/mcp \\
        --header "Authorization: Bearer $MCP_TOKEN"

Make it reachable from the internet (claude.ai custom connectors, a classmate's laptop):
    cloudflared tunnel --url http://localhost:8000                # or: ngrok http 8000 → an https URL
    PUBLIC_HOST=<the-tunnel-host> python challenge/mcp_live/step4_remote.py
    claude.ai → Customize → Connectors → Add custom connector → URL https://<the-tunnel-host>/mcp
              → No sign in → Request headers: Authorization = Bearer <your token>

AUTH, the way the MCP spec describes it
  The server is an OAuth 2.1 *resource server*. A request with no token or a bad one gets
  HTTP 401 + a WWW-Authenticate header that points to /.well-known/oauth-protected-resource,
  and that document names the authorization server that issues tokens. A client like Claude Code
  or claude.ai can then run the OAuth login in the browser by itself.
  In this demo the "authorization server" is you, handing out ONE shared secret: fine for a class,
  not for production. In production you use a real OAuth provider (Auth0, Microsoft Entra ID,
  Amazon Cognito, Keycloak…) and a verifier that checks the token's signature, expiry and audience.

These are real CVs: run a public tunnel only for the demo, with a token, and stop it afterwards.
"""
import hmac
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from mcp.server.auth.provider import AccessToken                    # noqa: E402
from mcp.server.auth.settings import AuthSettings                   # noqa: E402
from mcp.server.fastmcp import FastMCP                              # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

TOKEN = os.getenv("MCP_TOKEN") or sys.exit("Set MCP_TOKEN first, e.g.  export MCP_TOKEN=$(python -c \"import secrets; print(secrets.token_urlsafe(24))\")")
PORT = int(os.getenv("PORT", "8000"))
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "")                          # e.g. abc-123.trycloudflare.com
BASE = f"https://{PUBLIC_HOST}" if PUBLIC_HOST else f"http://127.0.0.1:{PORT}"

import step3_full as tools                                          # noqa: E402  the SAME tools as step 3


class SharedSecret:
    """The token check. FastMCP calls it for EVERY request; None = refuse with 401."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if hmac.compare_digest(token.encode(), TOKEN.encode()):   # constant-time compare
            return AccessToken(token=token, client_id="class-demo", scopes=["cvs:read"],
                               expires_at=int(time.time()) + 3600, resource=f"{BASE}/mcp")
        return None


mcp = FastMCP(
    "cv-remote",
    instructions=tools.mcp.instructions,
    host="127.0.0.1", port=PORT,                                    # listen locally; a tunnel brings the internet in
    token_verifier=SharedSecret(),
    auth=AuthSettings(issuer_url=os.getenv("AUTH_ISSUER", BASE),    # who issues tokens (here: you)
                      resource_server_url=f"{BASE}/mcp",            # this server's address, for the 401 metadata
                      required_scopes=["cvs:read"],
                      validate_token_resource=True),                # refuse tokens issued for another server
    # Only answer requests addressed to us (blocks DNS-rebinding attacks from a web page):
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"] + ([PUBLIC_HOST] if PUBLIC_HOST else []),
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*"] + ([f"https://{PUBLIC_HOST}"] if PUBLIC_HOST else [])),
)

for fn in (tools.search_cvs, tools.find_candidates, tools.get_cv):
    mcp.tool()(fn)

if __name__ == "__main__":
    print(f"cv-remote listening on http://127.0.0.1:{PORT}/mcp" + (f"  ·  public: {BASE}/mcp" if PUBLIC_HOST else ""), file=sys.stderr)
    mcp.run(transport="streamable-http")
