"""Aerith self-maintenance: watch logs, draft fixes, offer feature updates.

Aerith may *draft* changes on her own, but nothing she writes reaches the
running app until a human admin approves it.  See companion/maintenance/README.md.
"""

from companion.maintenance.config import MaintenanceConfig
from companion.maintenance.store import MaintenanceStore

__all__ = ["MaintenanceConfig", "MaintenanceStore"]
