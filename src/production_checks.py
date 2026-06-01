"""Pre-flight checks before running against production Nodum / RRHH."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.loader import nodum_read_is_configured
from src.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProductionCheckResult:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def run_production_checks(settings: Settings, *, strict: bool) -> ProductionCheckResult:
    """
    Validate settings for a production run.

    strict=True (SYNC_PRODUCTION=1): treat blocking issues as errors (exit 1).
    strict=False: log warnings only for non-fatal misconfigurations.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if settings.nodum_dry_run:
        msg = "NODUM_DRY_RUN is on; no SOAP calls will be made. Set NODUM_DRY_RUN=0 for production."
        (errors if strict else warnings).append(msg)

    if settings.sync_test_date is not None:
        msg = (
            f"SYNC_TEST_DATE={settings.sync_test_date.isoformat()} is set; "
            "remove it for production (uses real calendar day)."
        )
        (errors if strict else warnings).append(msg)

    if settings.sync_force_run:
        msg = "SYNC_FORCE_RUN is on; weekend/holiday gate is disabled."
        warnings.append(msg)

    if settings.nodum_parte_scope == "backfill" and strict:
        warnings.append(
            "NODUM_PARTE_SCOPE=backfill in production: prefer 'today' for daily Task Scheduler "
            "(backfill only for initial catch-up, then switch to today)."
        )

    if not nodum_read_is_configured(settings):
        warnings.append(
            "NODUM_READ_OPERATION is empty: cannot skip days already loaded in Nodum "
            "(only local state file)."
        )

    wsdl = settings.nodum_wsdl.lower()
    if "amaral01" not in wsdl:
        warnings.append(
            f"NODUM_WSDL_URL does not contain 'Amaral01' ({settings.nodum_wsdl!r}). "
            "Confirm this is the correct Nodum instance."
        )

    read_wsdl = (settings.nodum_read_wsdl or settings.nodum_wsdl).lower()
    if nodum_read_is_configured(settings) and "amaral01" not in read_wsdl:
        warnings.append(
            "NODUM_READ_WSDL_URL does not contain 'Amaral01'; read-back may use wrong environment."
        )

    if not settings.nodum_read_match_resolved_proyecto:
        warnings.append(
            "NODUM_READ_MATCH_RESOLVED_PROYECTO=0: all titular hours count toward 'complete' "
            "(may skip maternity loads). Keep enabled in production."
        )

    return ProductionCheckResult(
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def log_production_checks(result: ProductionCheckResult) -> None:
    for w in result.warnings:
        logger.warning("Production check: %s", w)
    for e in result.errors:
        logger.error("Production check (blocking): %s", e)
