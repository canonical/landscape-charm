

def is_valid_url(value):
    """
    A helper to validate a string is a URL suitable to use as root-url.
    """
    if not value[-1] == "/":
        return False
    if not value.startswith("http"):
        return False
    if "://" not in value:
        return False

    return True
