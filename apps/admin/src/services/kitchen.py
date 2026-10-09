from __future__ import annotations

import uuid
from datetime import datetime

from exceptions import InvalidKitchenDocumentError
from models import KitchenExport
from repositories import KitchenRepository
from schemas.kitchen import (
    KitchenExportDetail,
    KitchenExportLineInput,
    KitchenExportRow,
    KitchenProductionLineInput,
    KitchenProductionDetail,
    KitchenProductionRow,
)


class KitchenService:
    def __init__(self, repository: KitchenRepository) -> None:
        self._repository = repository

    def list_exports(self) -> list[KitchenExportRow]:
        return self._repository.list_exports()

    def list_productions(self) -> list[KitchenProductionRow]:
        return self._repository.list_productions()

    def analytics_rows(self, direction: str, start: datetime | None, end: datetime | None):
        return self._repository.analytics_rows(direction, start, end)

    def get_production_detail(self, production_id: uuid.UUID) -> KitchenProductionDetail:
        result = self._repository.get_production_detail(production_id)
        if result is None:
            raise ValueError("Kitchen production document not found")
        return KitchenProductionDetail(*result)

    def create_production(self, user_id: uuid.UUID, notes: str | None, lines: list[KitchenProductionLineInput]):
        return self._repository.create_production(user_id, notes, lines)

    def get_detail(self, export_id: uuid.UUID) -> KitchenExportDetail:
        result = self._repository.get_detail(export_id)
        if result is None:
            raise ValueError("Kitchen document not found")
        return KitchenExportDetail(*result)

    def create_draft(
        self, user_id: uuid.UUID, notes: str | None, lines: list[KitchenExportLineInput]
    ) -> KitchenExport:
        try:
            return self._repository.create_draft(user_id, notes, lines)
        except ValueError as exc:
            raise InvalidKitchenDocumentError(str(exc)) from exc

    def update_draft(
        self,
        export_id: uuid.UUID,
        notes: str | None,
        lines: list[KitchenExportLineInput],
    ) -> KitchenExport:
        try:
            return self._repository.update_draft(export_id, notes, lines)
        except ValueError as exc:
            raise InvalidKitchenDocumentError(str(exc)) from exc

    def lock(self, export_id: uuid.UUID) -> KitchenExport:
        try:
            return self._repository.lock(export_id)
        except ValueError as exc:
            raise InvalidKitchenDocumentError(str(exc)) from exc

    def reopen_for_edit(self, export_id: uuid.UUID) -> KitchenExport:
        try:
            return self._repository.reopen_for_edit(export_id)
        except ValueError as exc:
            raise InvalidKitchenDocumentError(str(exc)) from exc
