import random
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("RandomBeta")

@mcp.tool()
def get_random_beta() -> int:
    """Get a random number between 1 and 100 from Beta source"""
    return random.randint(1, 100)

if __name__ == "__main__":
    mcp.run()
