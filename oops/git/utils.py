import re


def extract_submodule_name(line: str) -> str:
    """Extract submodule name from a ConfigParser section line.

    Args:
        line: Section line like 'submodule "NAME"'

    Returns:
        Submodule name or None if not found
    """
    match = re.search(r'submodule\s+"([^"]+)"', line)

    if not match:
        raise ValueError(f"Invalid submodule line: {line}")

    name = match.group(1)
    return name
