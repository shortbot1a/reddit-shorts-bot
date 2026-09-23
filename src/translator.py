"""
translator.py
--------------
Traducción EN<->ES 100% local y gratuita para siempre, usando Argos
Translate (motor de traducción neuronal open-source que corre offline,
sin API key, sin límite de uso y sin coste).

IMPORTANTE: deliberadamente NO se usa aquí un modelo de IA por API
(Claude, GPT, etc.) para traducir en el pipeline recurrente, aunque el
usuario mencionó esa posibilidad. Los planes gratuitos de las APIs de IA
son créditos de prueba, no un tier gratuito permanente, así que usarlos
violaría el requisito de "coste cero para siempre, sin trials". Argos
Translate sí lo cumple: se instala una vez y funciona sin conexión.
"""

from __future__ import annotations

import re
import logging
import argostranslate.package
import argostranslate.translate

logger = logging.getLogger("translator")

_INSTALLED = False


def ensure_language_pair(from_code: str = "en", to_code: str = "es"):
    """Descarga e instala el paquete de idioma la primera vez que se necesita.
    Las siguientes ejecuciones ya lo encuentran instalado y no vuelven a
    descargar nada (por eso el pipeline recurrente no depende de red para esto
    salvo la primerísima vez)."""
    global _INSTALLED
    installed_languages = argostranslate.translate.get_installed_languages()
    have_pair = any(
        lang.code == from_code and lang.get_translation(
            next((l for l in installed_languages if l.code == to_code), None)
        )
        for lang in installed_languages
    )
    if have_pair:
        return

    logger.info("Descargando paquete de traducción %s->%s (solo la primera vez)...", from_code, to_code)
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    package = next(
        p for p in available_packages if p.from_code == from_code and p.to_code == to_code
    )
    argostranslate.package.install_from_path(package.download())
    logger.info("Paquete %s->%s instalado.", from_code, to_code)


def _split_sentences(text: str) -> list[str]:
    # División simple por frase; suficiente para no exceder el contexto del
    # traductor y mantener naturalidad. Conserva saltos de párrafo.
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def translate_text(text: str, from_code: str = "en", to_code: str = "es") -> str:
    if not text.strip():
        return ""
    ensure_language_pair(from_code, to_code)
    installed_languages = argostranslate.translate.get_installed_languages()
    src = next(l for l in installed_languages if l.code == from_code)
    tgt = next(l for l in installed_languages if l.code == to_code)
    translation = src.get_translation(tgt)

    # Traducimos por frases para evitar cortes de contexto en textos largos
    # y para poder paralelizar/depurar frase a frase si algo falla.
    sentences = _split_sentences(text)
    translated = [translation.translate(s) for s in sentences]
    return " ".join(translated)


def translate_story(title: str, body: str, from_code: str = "en", to_code: str = "es") -> tuple[str, str]:
    """Traduce título y cuerpo por separado (el título suele necesitar un
    tono más directo/llamativo, por eso no se concatenan)."""
    return translate_text(title, from_code, to_code), translate_text(body, from_code, to_code)


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    t, b = translate_story(
        "AITA for telling my roommate her cooking smells bad?",
        "Last week my roommate started making a dish every night that smells "
        "really strong. I asked her to stop but she got upset with me.",
    )
    print(t)
    print(b)
