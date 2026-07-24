
import sys
import logging
from fastmcp import FastMCP
mcp = FastMCP('test')

# Silence everything
logging.getLogger('fastmcp').setLevel(logging.CRITICAL)
logging.getLogger('mcp').setLevel(logging.CRITICAL)

mcp.run(show_banner=False)
