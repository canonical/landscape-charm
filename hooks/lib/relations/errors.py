class UnitDataNotReadyError(Exception):
    """Raised by custom RelationContext._is_ready when a unit is not ready."""
