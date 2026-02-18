import random
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("RandomGamma")

@mcp.tool()
def get_random_gamma() -> int:
    """Get a random number between 1 and 100 from Gamma source"""
    return random.randint(1, 100)

if __name__ == "__main__":
    mcp.run()
