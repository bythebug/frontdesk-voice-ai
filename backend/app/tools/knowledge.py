"""Knowledge-base search tool (Postgres full-text search, no vector DB)."""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tool_registry import registry
from app.db.repositories import KnowledgeBaseRepository


class SearchKnowledgeBaseInput(BaseModel):
    query: str


class KnowledgeArticleOut(BaseModel):
    category: str
    title: str
    content: str


class SearchKnowledgeBaseOutput(BaseModel):
    results: list[KnowledgeArticleOut]


@registry.register(
    "search_knowledge_base",
    "Search the clinic's knowledge base (hours, services, policies, insurance, parking, "
    "emergencies, pricing) for information to answer a patient's question.",
    SearchKnowledgeBaseInput,
)
async def search_knowledge_base(
    session: AsyncSession, args: SearchKnowledgeBaseInput
) -> SearchKnowledgeBaseOutput:
    articles = await KnowledgeBaseRepository(session).search(args.query)
    return SearchKnowledgeBaseOutput(
        results=[
            KnowledgeArticleOut(category=a.category, title=a.title, content=a.content)
            for a in articles
        ]
    )
