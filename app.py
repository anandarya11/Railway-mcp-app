"""
Indian Railway MCP Assistant — Streamlit front-end
----------------------------------------------------
Replicates the Cursor IDE / Composio Playground workflow from the project
cheat sheet, but as a shareable Streamlit web app:

  user prompt -> Claude (with MCP tools attached) -> MCP server call(s)
  -> formatted answer

MCP server: https://railway-mcp.amithv.xyz/mcp
"""

import asyncio
import streamlit as st
from anthropic import Anthropic
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "https://railway-mcp.amithv.xyz/mcp"
MODEL = "claude-sonnet-4-6"

st.set_page_config(page_title="Indian Railway MCP Assistant", page_icon="🚆")
st.title("🚆 Indian Railway MCP Assistant")
st.caption("Ask about train schedules, seat availability, or live status.")

with st.sidebar:
    st.header("Setup")
    api_key = st.text_input("Anthropic API key", type="password")
    st.markdown(
        "Get a key from the "
        "[Anthropic Console](https://console.anthropic.com/settings/keys)."
    )
    st.divider()
    st.markdown("**Example prompts**")
    st.code("Give me the Hyderabad to Tirupati scheduled trains list on 2025-07-20")
    st.code("Get the train info: KRISHNA EXP")
    st.code("Get seat availability of KRISHNA EXP from Hyderabad to Tirupati on 2025-07-20")
    st.code("Get train live status on date: 2025-07-17 train number: 17230 (SABARI EXPRESS)")


async def ask_mcp(prompt: str, api_key: str) -> tuple[str, list[str]]:
    """Send prompt to Claude with the Railway MCP tools attached, run any
    tool calls against the live MCP server, and return the final answer
    plus a log of which tools were called (for a Cursor-style trace)."""
    client = Anthropic(api_key=api_key)
    tool_log: list[str] = []

    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_resp = await session.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in tools_resp.tools
            ]

            messages = [{"role": "user", "content": prompt}]
            response = client.messages.create(
                model=MODEL, max_tokens=2000, tools=tools, messages=messages
            )

            while response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_log.append(f"Called {block.name}({block.input})")
                        result = await session.call_tool(block.name, block.input)
                        result_text = "\n".join(
                            part.text for part in result.content if hasattr(part, "text")
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            }
                        )
                messages.append({"role": "user", "content": tool_results})
                response = client.messages.create(
                    model=MODEL, max_tokens=2000, tools=tools, messages=messages
                )

            final_text = "\n".join(
                block.text for block in response.content if block.type == "text"
            )
            return final_text, tool_log


prompt = st.text_area("Your prompt", placeholder="Get the train info: KRISHNA EXP", height=80)
submitted = st.button("Submit", type="primary")

if submitted:
    if not api_key:
        st.error("Add your Anthropic API key in the sidebar first.")
    elif not prompt.strip():
        st.error("Type a prompt first.")
    else:
        with st.spinner("Calling the Indian Railway MCP server..."):
            try:
                answer, tool_log = asyncio.run(ask_mcp(prompt, api_key))
            except Exception as e:
                st.error(f"Something went wrong: {type(e).__name__}: {e}")

                if isinstance(e, BaseExceptionGroup):
                    st.write("### Detailed error:")

                    def show_error(exc):
                        if isinstance(exc, BaseExceptionGroup):
                            for sub in exc.exceptions:
                                show_error(sub)
                        else:
                            st.code(f"{type(exc).__name__}: {exc}")

                    show_error(e)
            else:
                if tool_log:
                    with st.expander("Tool calls (like the Cursor IDE trace)"):
                        for entry in tool_log:
                            st.code(entry, language="text")
                st.markdown("### Response")
                st.markdown(answer)
