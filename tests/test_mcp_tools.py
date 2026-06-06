import sys
import json
import subprocess
import time

SERVER_CMD = ["uv", "run", "arxiv-mcp-server"]


def rpc_request(req_id, method, params=None):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


def test_tools():
    proc = subprocess.Popen(
        SERVER_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/home/younesbensafia/my_github/arxiv-mcp-server",
    )

    def send(msg):
        proc.stdin.write((msg + "\n").encode())
        proc.stdin.flush()
        time.sleep(0.5)

    def recv(timeout=5):
        import select
        lines = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            r, _, _ = select.select([proc.stdout], [], [], 0.3)
            if r:
                line = proc.stdout.readline()
                if line:
                    lines.append(line.strip())
            if len(lines) >= 2:
                break
        return [json.loads(l) for l in lines]

    errors = []

    # Initialize
    send(rpc_request(1, "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    }))
    resp = recv()
    if not resp or "result" not in resp[0]:
        errors.append("Initialize failed")
        proc.kill()
        return errors

    # Send initialized notification
    send(rpc_request(None, "notifications/initialized"))

    # Test each tool
    tests = [
        ("search_arxiv", {"keyword": "quantum", "max_results": 2}),
        ("get_paper", {"arxiv_id": "2301.07041"}),
        ("get_recent", {"category": "cs.AI", "max_results": 2}),
        ("search_papers", {"query": "transformer", "max_results": 2}),
        ("fetch_pdf", {"arxiv_id": "2301.07041"}),
    ]

    req_id = 10
    for name, args in tests:
        req_id += 1
        send(rpc_request(req_id, "tools/call", {"name": name, "arguments": args}))
        resp = recv(timeout=30 if name == "fetch_pdf" else 10)

        if not resp:
            errors.append(f"{name}: no response")
            continue

        msg = resp[-1] if len(resp) > 1 else resp[0]

        if "error" in msg:
            errors.append(f"{name}: RPC error: {msg['error']}")
            continue

        result = msg.get("result", {})
        content = result.get("content", [])

        if not isinstance(content, list):
            errors.append(f"{name}: content is not a list")
            continue

        if len(content) == 0:
            errors.append(f"{name}: empty content array")
            continue

        item = content[0]
        if item.get("type") != "text":
            errors.append(f"{name}: first content item type is '{item.get('type')}', expected 'text'")
            continue

        text = item.get("text", "")
        if text.startswith("Error:"):
            errors.append(f"{name}: tool returned error: {text[:100]}")
            continue

        print(f"  PASS  {name}  ({len(text)} chars)")

    proc.kill()
    return errors


if __name__ == "__main__":
    print("Testing MCP tool response shapes...\n")
    errs = test_tools()
    print(f"\n{'=' * 40}")
    if errs:
        print(f"FAILED: {len(errs)} errors")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("ALL TOOLS PASSED")
