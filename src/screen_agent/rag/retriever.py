"""Knowledge retriever for RAG system.

Provides retrieval interface for augmenting agent prompts with
relevant knowledge.
"""

from typing import List, Optional
from .knowledge_store import KnowledgeStore, KnowledgeEntry, KnowledgeType
from ..utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeRetriever:
    """
    Retrieves relevant knowledge to augment agent prompts.

    Provides context-aware retrieval based on:
    - Current task description
    - Current application context
    - Recent actions and observations
    """

    def __init__(self, knowledge_store: Optional[KnowledgeStore] = None):
        """
        Initialize retriever.

        Args:
            knowledge_store: Knowledge store instance (creates default if None)
        """
        self.store = knowledge_store or KnowledgeStore()

    def retrieve_for_task(
        self,
        task: str,
        top_k: int = 3,
        min_score: float = 0.15
    ) -> str:
        """
        Retrieve relevant knowledge for a task.

        Args:
            task: Task description
            top_k: Maximum number of entries to retrieve
            min_score: Minimum relevance score

        Returns:
            Formatted knowledge context string
        """
        entries = self.store.search(task, top_k=top_k, min_score=min_score)

        if not entries:
            return ""

        return self._format_entries(entries)

    def retrieve_for_action(
        self,
        action_context: str,
        app_name: Optional[str] = None,
        top_k: int = 2
    ) -> str:
        """
        Retrieve knowledge relevant to current action context.

        Args:
            action_context: Description of current action/situation
            app_name: Current application name
            top_k: Maximum number of entries

        Returns:
            Formatted knowledge context string
        """
        entries = self.store.search(
            action_context,
            top_k=top_k,
            app_name=app_name,
            min_score=0.1
        )

        if not entries:
            return ""

        return self._format_entries(entries)

    def retrieve_for_error(
        self,
        error_description: str,
        top_k: int = 2
    ) -> str:
        """
        Retrieve knowledge for handling errors.

        Args:
            error_description: Description of the error
            top_k: Maximum number of entries

        Returns:
            Formatted knowledge context string
        """
        # First try error handling knowledge
        entries = self.store.search(
            error_description,
            top_k=top_k,
            knowledge_type=KnowledgeType.ERROR_HANDLING,
            min_score=0.1
        )

        # If not enough, add tips
        if len(entries) < top_k:
            tips = self.store.search(
                error_description,
                top_k=top_k - len(entries),
                knowledge_type=KnowledgeType.TIP,
                min_score=0.1
            )
            entries.extend(tips)

        if not entries:
            return ""

        return self._format_entries(entries)

    def get_app_guide(self, app_name: str) -> str:
        """
        Get guide for a specific application.

        Args:
            app_name: Application name

        Returns:
            Formatted guide string
        """
        entries = self.store.get_by_app(app_name)

        if not entries:
            return ""

        return self._format_entries(entries)

    def get_shortcuts(self, query: Optional[str] = None) -> str:
        """
        Get relevant keyboard shortcuts.

        Args:
            query: Optional query to filter shortcuts

        Returns:
            Formatted shortcuts string
        """
        if query:
            entries = self.store.search(
                query,
                top_k=2,
                knowledge_type=KnowledgeType.SHORTCUT,
                min_score=0.05
            )
        else:
            entries = self.store.get_by_type(KnowledgeType.SHORTCUT)

        if not entries:
            return ""

        return self._format_entries(entries)

    def _format_entries(self, entries: List[KnowledgeEntry]) -> str:
        """Format knowledge entries for prompt injection."""
        if not entries:
            return ""

        lines = ["=== 相关知识参考 ==="]
        for entry in entries:
            lines.append(f"\n### {entry.title}")
            lines.append(entry.content)
        lines.append("\n=== 知识参考结束 ===")

        return "\n".join(lines)


def create_rag_context(
    task: str,
    current_app: Optional[str] = None,
    current_action: Optional[str] = None,
    error: Optional[str] = None,
    retriever: Optional[KnowledgeRetriever] = None
) -> str:
    """
    Convenience function to create RAG context for prompts.

    Args:
        task: Current task description
        current_app: Current application name
        current_action: Current action being attempted
        error: Error description if any
        retriever: Knowledge retriever instance

    Returns:
        Combined knowledge context string
    """
    if retriever is None:
        retriever = KnowledgeRetriever()

    contexts = []

    # Task-level knowledge
    task_knowledge = retriever.retrieve_for_task(task, top_k=2)
    if task_knowledge:
        contexts.append(task_knowledge)

    # Action-specific knowledge
    if current_action:
        action_knowledge = retriever.retrieve_for_action(
            current_action,
            app_name=current_app,
            top_k=1
        )
        if action_knowledge and action_knowledge not in contexts:
            contexts.append(action_knowledge)

    # Error handling knowledge
    if error:
        error_knowledge = retriever.retrieve_for_error(error, top_k=1)
        if error_knowledge and error_knowledge not in contexts:
            contexts.append(error_knowledge)

    return "\n\n".join(contexts)
