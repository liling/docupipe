from __future__ import annotations


class TypeRuleResolver:
    def __init__(
        self,
        extension_rules: dict[str, str],
        mime_rules: dict[str, str] | None = None,
    ):
        self._extension_rules = extension_rules
        self._mime_rules = mime_rules or {}

    def resolve(self, extension: str, mime_type: str = "") -> str | None:
        if extension in self._extension_rules:
            return self._extension_rules[extension]
        if mime_type and mime_type in self._mime_rules:
            return self._mime_rules[mime_type]
        return None
