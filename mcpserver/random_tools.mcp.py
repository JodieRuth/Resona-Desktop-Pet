import random
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("RandomTools")

@mcp.tool()
def get_random_numbers(min_val: int, max_val: int, count: int = 1) -> list[int]:
    """Generate a list of random integers within a specified range (inclusive).
    
    Args:
        min_val: The minimum value (inclusive).
        max_val: The maximum value (inclusive).
        count: The number of random integers to generate. Defaults to 1.
    """
    try:
        if count < 1:
            return []
        if min_val > max_val:
            return []
            
        return [random.randint(min_val, max_val) for _ in range(count)]
    except Exception:
        return []

if __name__ == "__main__":
    mcp.run()
