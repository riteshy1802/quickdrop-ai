"""One bounded LangGraph, with PostgreSQL as the only durable state authority."""

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import Nodes
from app.agent.routes import after_understanding
from app.agent.state import AgentState
from app.agent.tools import AgentTools


def build_graph(tools, *, extractor=None):
    nodes = Nodes(tools, extractor)
    graph = StateGraph(AgentState)
    graph.add_node("load_context", nodes.load_context)
    graph.add_node("understand", nodes.understand)
    graph.add_node("investigate", nodes.investigate)
    graph.add_node("reply", nodes.reply)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "understand")
    graph.add_conditional_edges(
        "understand", after_understanding, {"reply": "reply", "investigate": "investigate"}
    )
    graph.add_edge("investigate", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


async def run_agent(factory, claimed, *, client=None, extractor=None):
    tools = AgentTools(factory, claimed, client)
    result = await build_graph(tools, extractor=extractor).ainvoke(
        {
            "rider_id": claimed.rider_id,
            "conversation_id": claimed.conversation_id,
            "message_id": claimed.message_id,
        },
        config={"recursion_limit": 8, "callbacks": []},
    )
    return result["reply"]
