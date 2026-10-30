"""Routes for the service-wide configuration template."""

from fastapi import APIRouter

from seamus.config.models import AgentConfig
from seamus.config.template import get_config_template_store
from seamus.server.schemas import ConfigTemplateResponse

router = APIRouter(prefix="/config-template", tags=["config-template"])


@router.get("", response_model=ConfigTemplateResponse)
async def get_config_template() -> ConfigTemplateResponse:
    """Retrieve the current singleton configuration template."""
    store = get_config_template_store()
    template = store.get_template()
    return ConfigTemplateResponse(
        config=template,
        is_complete=template.is_complete(),
    )


@router.post("", response_model=ConfigTemplateResponse)
async def update_config_template(payload: AgentConfig) -> ConfigTemplateResponse:
    """Set or replace the singleton configuration template with a full updated object."""
    store = get_config_template_store()
    updated = store.set_template(payload)
    return ConfigTemplateResponse(
        config=updated,
        is_complete=updated.is_complete(),
    )

