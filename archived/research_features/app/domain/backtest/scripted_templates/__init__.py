from app.domain.backtest.scripted_templates.registry import (
    get_template_runtime,
    is_scripted_template,
    require_scripted_template,
    template_builder_kind,
    template_supports_paper,
    template_supports_version_editing,
)

__all__ = [
    "get_template_runtime",
    "is_scripted_template",
    "require_scripted_template",
    "template_builder_kind",
    "template_supports_paper",
    "template_supports_version_editing",
]
