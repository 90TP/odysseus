# services/memory/__init__.py
"""Memory service — persistent memory storage and retrieval."""

from .service import MemoryService, Memory, MemorySearchResult
from .memory import MemoryManager, MemoryStoreUnreadable
from .memory_vector import MemoryVectorStore
from .skill_evolution import SkillEvolutionError, SkillEvolutionManager
from .skill_evolution_promotion import apply as _apply_skill_evolution_promotion

_apply_skill_evolution_promotion(SkillEvolutionManager)

__all__ = [
    "MemoryService",
    "Memory",
    "MemorySearchResult",
    "MemoryManager",
    "MemoryStoreUnreadable",
    "MemoryVectorStore",
    "SkillEvolutionError",
    "SkillEvolutionManager",
]
