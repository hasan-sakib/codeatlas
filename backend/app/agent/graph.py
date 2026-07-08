from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes.assess_sufficiency import assess_sufficiency_edge, assess_sufficiency_node
from app.agent.nodes.call_tool import call_tool_node
from app.agent.nodes.cite_sources import cite_sources_node
from app.agent.nodes.classify_intent import classify_intent_edge, classify_intent_node
from app.agent.nodes.error_handler import error_handler_node
from app.agent.nodes.finalize import finalize_node
from app.agent.nodes.generate_answer import generate_answer_node
from app.agent.nodes.rerank import rerank_node
from app.agent.nodes.retrieve_context import retrieve_context_node
from app.agent.nodes.rewrite_query import rewrite_query_node
from app.agent.nodes.tool_router import tool_router_edge, tool_router_node
from app.agent.state import AgentState
from app.agent.tools.get_file_tool import GetFileTool
from app.agent.tools.get_git_blame_tool import GetGitBlameTool
from app.agent.tools.run_search_tool import RunSearchTool
from app.application.services.retrieval_service import RetrievalService
from app.application.use_cases.chat.manage_conversation import ManageConversationUseCase
from app.core.config import AgentSettings
from app.domain.ports.llm_port import LLMPort
from app.domain.ports.reranker_port import RerankerPort
from app.infrastructure.llm.prompt_renderer import PromptRenderer


def _route_or_error(state: AgentState, *, happy_path: str) -> str:
    return "error_handler" if state.get("error") else happy_path


def build_agent_graph(
    llm_port: LLMPort,
    retrieval_service: RetrievalService,
    reranker_port: RerankerPort,
    manage_conversation_use_case: ManageConversationUseCase,
    prompt_renderer: PromptRenderer,
    get_file_tool: GetFileTool,
    get_git_blame_tool: GetGitBlameTool,
    run_search_tool: RunSearchTool,
    settings: AgentSettings,
) -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node(
        "classify_intent",
        partial(
            classify_intent_node,
            llm_port=llm_port,
            prompt_renderer=prompt_renderer,
            settings=settings,
        ),
    )
    graph.add_node(
        "rewrite_query",
        partial(
            rewrite_query_node,
            llm_port=llm_port,
            prompt_renderer=prompt_renderer,
            settings=settings,
        ),
    )
    graph.add_node(
        "retrieve_context",
        partial(retrieve_context_node, retrieval_service=retrieval_service, settings=settings),
    )
    graph.add_node("rerank", partial(rerank_node, reranker_port=reranker_port))
    graph.add_node("assess_sufficiency", assess_sufficiency_node)
    graph.add_node("tool_router", partial(tool_router_node, settings=settings))
    graph.add_node(
        "call_tool",
        partial(
            call_tool_node,
            get_file_tool=get_file_tool,
            get_git_blame_tool=get_git_blame_tool,
            run_search_tool=run_search_tool,
        ),
    )
    graph.add_node(
        "generate_answer",
        partial(
            generate_answer_node,
            llm_port=llm_port,
            prompt_renderer=prompt_renderer,
            settings=settings,
        ),
    )
    graph.add_node("cite_sources", cite_sources_node)
    graph.add_node(
        "finalize",
        partial(finalize_node, manage_conversation_use_case=manage_conversation_use_case),
    )
    graph.add_node("error_handler", error_handler_node)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        classify_intent_edge,
        {
            "error_handler": "error_handler",
            "rewrite_query": "rewrite_query",
            "generate_answer": "generate_answer",
        },
    )
    graph.add_conditional_edges(
        "rewrite_query",
        partial(_route_or_error, happy_path="retrieve_context"),
        {"error_handler": "error_handler", "retrieve_context": "retrieve_context"},
    )
    graph.add_conditional_edges(
        "retrieve_context",
        partial(_route_or_error, happy_path="rerank"),
        {"error_handler": "error_handler", "rerank": "rerank"},
    )
    graph.add_edge("rerank", "assess_sufficiency")
    graph.add_conditional_edges(
        "assess_sufficiency",
        partial(assess_sufficiency_edge, settings=settings),
        {"retrieve_context": "retrieve_context", "tool_router": "tool_router"},
    )
    graph.add_conditional_edges(
        "tool_router",
        tool_router_edge,
        {"call_tool": "call_tool", "generate_answer": "generate_answer"},
    )
    graph.add_edge("call_tool", "tool_router")
    graph.add_conditional_edges(
        "generate_answer",
        partial(_route_or_error, happy_path="cite_sources"),
        {"error_handler": "error_handler", "cite_sources": "cite_sources"},
    )
    graph.add_edge("cite_sources", "finalize")
    graph.add_edge("error_handler", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
