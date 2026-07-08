from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "prompt_templates"


class PromptRenderer:
    def __init__(self, templates_dir: Path = _DEFAULT_TEMPLATES_DIR) -> None:
        # StrictUndefined: a missing template variable raises immediately
        # (jinja2.UndefinedError) instead of silently rendering an empty
        # string into the prompt sent to the LLM.
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=False,  # noqa: S701 — plain-text LLM prompts, not HTML
            undefined=StrictUndefined,
        )

    def render(self, template_name: str, **context: object) -> str:
        return self._env.get_template(template_name).render(**context)
