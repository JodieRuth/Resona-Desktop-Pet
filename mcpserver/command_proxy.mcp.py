import subprocess
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("CommandProxy")


def _run_cmd(command: str, timeout: int, cwd: str) -> str:
    completed = subprocess.run(
        ["cmd", "/c", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=cwd or None
    )
    return _format_result(completed.returncode, completed.stdout, completed.stderr)


def _run_powershell(command: str, timeout: int, cwd: str) -> str:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=cwd or None
    )
    return _format_result(completed.returncode, completed.stdout, completed.stderr)


def _format_result(code: int, stdout: str, stderr: str) -> str:
    parts = [f"exit_code={code}"]
    if stdout:
        parts.append("stdout:")
        parts.append(stdout)
    if stderr:
        parts.append("stderr:")
        parts.append(stderr)
    return "\n".join(parts).strip()


@mcp.tool()
def exec_shell(raw: str, timeout: int = 30, cwd: str = "") -> str:
    """Execute a shell command. Usage: 'cmd <command>' or 'powershell <command>'. Returns stdout/stderr."""
    try:
        if not raw:
            return "Error: Empty command"
        parts = raw.strip().split(" ", 1)
        if len(parts) < 2:
            return "Error: Use format 'cmd <command>' or 'powershell <command>'"
        mode, command = parts[0].lower(), parts[1]
        if cwd:
            target = Path(cwd)
            if not target.exists() or not target.is_dir():
                return f"Error: Invalid cwd: {cwd}"
        if mode == "cmd":
            return _run_cmd(command, timeout, cwd)
        if mode == "powershell":
            return _run_powershell(command, timeout, cwd)
        return "Error: Mode must be 'cmd' or 'powershell'"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()
