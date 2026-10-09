from __future__ import annotations

from repositories.waste import WasteRepository
from schemas.waste import WasteDetail


class WasteService:
    def __init__(self, repository: WasteRepository) -> None:
        self._repository = repository

    def list_documents(self):
        return self._repository.list_documents()

    def get_detail(self, document_id):
        result = self._repository.get_detail(document_id)
        if result is None:
            raise ValueError("Դուրսգրման փաստաթուղթը չի գտնվել։")
        return WasteDetail(*result)

    def create_draft(self, user_id, notes, lines, *, complete=False):
        return self._repository.create_draft(user_id, notes, lines, complete=complete)

    def update_draft(self, document_id, notes, lines, *, complete=False):
        return self._repository.update_draft(
            document_id, notes, lines, complete=complete
        )

    def lock(self, document_id):
        return self._repository.lock(document_id)

    def reopen_for_edit(self, document_id):
        return self._repository.reopen_for_edit(document_id)
