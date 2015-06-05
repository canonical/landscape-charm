class CharmError(Exception):
    """
    Base class for all internal charm errors.

    Inherit for errors that need to be gracefully reported
    in actions and hooks.
    """
