import re

VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


class MissingTemplateVariables(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Missing template variables: {', '.join(missing)}")


def extract_variables(text: str) -> list[str]:
    return sorted(set(VAR_PATTERN.findall(text)))


def render_template(text: str, variables: dict) -> str:
    required = extract_variables(text)
    missing = [v for v in required if v not in variables]
    if missing:
        raise MissingTemplateVariables(missing)

    def _sub(match: re.Match) -> str:
        return str(variables[match.group(1)])

    return VAR_PATTERN.sub(_sub, text)
