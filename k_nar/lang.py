"""Registro de IDIOMAS — mapeia idioma → vozes Piper + léxico.

Um `LanguageProfile` diz qual voz o narrador e os personagens usam e qual léxico o
Screenwriter aplica. Trocar de idioma = trocar de perfil; o resto do pipeline (EDL,
mix, ducking) é agnóstico. As vozes são baixadas por `scripts/download_lang.sh <lang>`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LanguageProfile:
    code: str                 # canônico, ex.: "pt_BR"
    lexicon: str              # chave para narrative.lexicons.get_lexicon
    main_voice: str           # modelo Piper dos personagens (em models/piper/)
    narrator_voice: str       # modelo Piper do narrador
    # (subpasta HF, voz, qualidade) — usado por scripts/download_lang.sh
    downloads: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    def voice_path(self, models_dir: str, narrator: bool = False) -> str:
        import os
        return os.path.join(models_dir, self.narrator_voice if narrator else self.main_voice)


LANGUAGES: dict[str, LanguageProfile] = {
    "pt": LanguageProfile(
        "pt_BR", "pt", "pt_BR-faber-medium.onnx", "pt_BR-jeff-medium.onnx",
        (("pt/pt_BR", "faber", "medium"), ("pt/pt_BR", "jeff", "medium"))),
    "en": LanguageProfile(
        "en_US", "en", "en_US-amy-medium.onnx", "en_US-ryan-medium.onnx",
        (("en/en_US", "amy", "medium"), ("en/en_US", "ryan", "medium"))),
    "es": LanguageProfile(
        "es_ES", "es", "es_ES-davefx-medium.onnx", "es_ES-sharvard-medium.onnx",
        (("es/es_ES", "davefx", "medium"), ("es/es_ES", "sharvard", "medium"))),
}

# apelidos aceitos (o front-matter/CLI pode dizer "portugues", "english", "es_ES"...)
_ALIASES = {
    "pt_br": "pt", "pt-br": "pt", "portugues": "pt", "português": "pt", "brazilian": "pt",
    "en_us": "en", "en-us": "en", "english": "en", "ingles": "en", "inglês": "en",
    "es_es": "es", "es-es": "es", "espanol": "es", "español": "es", "spanish": "es",
}


def get_language(lang: str) -> LanguageProfile:
    """Perfil do idioma (default pt). Aceita código, apelido ou nome."""
    key = str(lang or "pt").strip().lower().replace(" ", "")
    key = _ALIASES.get(key, key)
    return LANGUAGES.get(key, LANGUAGES["pt"])


def language_codes() -> list[str]:
    return list(LANGUAGES)
