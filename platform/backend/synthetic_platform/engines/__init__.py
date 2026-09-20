"""Engine registry. Importing this module registers every built-in adapter."""
from .base import (  # noqa: F401
    EngineAdapter,
    GenerationOutcome,
    available_engines,
    choose_engine,
    get_engine,
    register,
)
from . import rules  # noqa: F401  registers "rules"
from . import relational  # noqa: F401  registers "relational_rules"

try:  # arfpy is optional; the platform stays usable without it
    from . import learned  # noqa: F401  registers "arf" and "independent"

    ARF_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only where arfpy is absent
    ARF_AVAILABLE = False
