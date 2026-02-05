import re
from pathlib import Path


REQUIRED_PLACEHOLDERS = {'name', 'hospital'}
ALLOWED_PLACEHOLDERS = {'name', 'hospital', 'report_type', 'date', 'doctor'}

PLACEHOLDER_PATTERN = re.compile(r'\{(\w+)\}')


class TemplateError(Exception):
    """Raised when template validation fails."""
    pass


def extract_placeholders(template: str) -> set[str]:
    """Extract all placeholder names from a template string."""
    return set(PLACEHOLDER_PATTERN.findall(template))


def validate_template(template: str, provided_values: dict[str, str]) -> None:
    """
    Validate a template against provided values.

    Raises TemplateError if:
    - Template contains unknown placeholders
    - Required placeholders are missing from provided_values
    """
    placeholders_in_template = extract_placeholders(template)

    unknown_placeholders = placeholders_in_template - ALLOWED_PLACEHOLDERS
    if unknown_placeholders:
        raise TemplateError(
            f"Unknown placeholder(s) in template: {', '.join(sorted(unknown_placeholders))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_PLACEHOLDERS))}"
        )

    required_in_template = placeholders_in_template & REQUIRED_PLACEHOLDERS
    provided_keys = set(provided_values.keys())

    missing_required = required_in_template - provided_keys
    if missing_required:
        raise TemplateError(
            f"Missing required value(s): {', '.join(sorted(missing_required))}"
        )


def render_template(template: str, values: dict[str, str]) -> str:
    """
    Render a template by replacing placeholders with values.

    Optional placeholders that are not provided will be removed from the output.
    """
    result = template

    for placeholder in extract_placeholders(template):
        if placeholder in values and values[placeholder]:
            result = result.replace(f'{{{placeholder}}}', values[placeholder])
        else:
            result = result.replace(f'{{{placeholder}}}', '')

    result = re.sub(r'\s+', ' ', result).strip()

    return result


def load_template_from_file(file_path: Path) -> str:
    """
    Load a template from a file.

    Raises FileNotFoundError if the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Template file not found: {file_path}")

    return file_path.read_text(encoding='utf-8').strip()
