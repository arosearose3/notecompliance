"""Built-in rewrite actions. Import this module to register them."""

from compliance.rewrite.actions.provider_title import ProviderTitleAction
from compliance.rewrite.actions.supervisor_credential import SupervisorCredentialAction
from compliance.rewrite.registry import register_action

register_action(ProviderTitleAction())
register_action(SupervisorCredentialAction())

__all__ = ["ProviderTitleAction", "SupervisorCredentialAction"]
