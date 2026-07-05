from fastmcp import Client

from sber_a2a.mcp import create_mcp_server


async def test_mcp_exposes_a3_tools(container) -> None:
    server = create_mcp_server(container)

    async with Client(server) as client:
        tools = await client.list_tools()
        result = await client.call_tool("list_supplier_agents", {})

    names = {tool.name for tool in tools}
    assert names == {
        "list_supplier_agents",
        "create_procurement_deal",
        "get_procurement_deal",
        "approve_supplier_quote",
    }
    assert len(result.data) == 3
