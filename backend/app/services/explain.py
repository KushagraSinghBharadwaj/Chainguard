"""Optional plain-language rewrite of a report summary by a local LLM (Ollama).

The engine decides the risk level. This module only validates text: if the LLM
output fails any check, it is discarded and the engine summary is shown instead.
"""

import re

EXPLAIN_LEVELS = {"MODERATE", "HIGH", "CRITICAL"}
MAX_SENTENCES = 3
MAX_CHARS = 600

SYSTEM_PROMPT = (
    "You rewrite security findings for a non-technical user.\n"
    "Rules:\n"
    "- Use ONLY the facts provided. Never add facts, names, numbers or advice.\n"
    '- Start with exactly: "Risk level: <LEVEL>." using the level given, unchanged.\n'
    "- Then write at most 2 plain sentences. No bullets, headings, bold or lists.\n"
    "- Do not speculate. Never use the words could, might, potentially or may.\n"
    "- Do not say a contract is safe or unsafe.\n"
    "- Do not mention source names in square brackets."
)

_LEVEL_WORDS = ("LOW", "MODERATE", "HIGH", "CRITICAL", "INSUFFICIENT_DATA")

# A banned phrase is rejected only if the engine text itself does not contain it.
_BANNED = (
    r"\bcould\b", r"\bpotentially\b", r"\bmight\b", r"\bmay\b", r"\bpossibly\b",
    r"\bdrain\w*", r"\bsteal\w*", r"\bstolen\b", r"\bhack\w*", r"\bscam\w*",
    r"\brug\s?pull\w*", r"transfer funds", r"\bunsafe\b", r"\bsafe\b", r"\bsafely\b",
    r"\bguarantee\w*", r"\bmalicious\w*",
)


def should_explain(report: dict) -> bool:
    return report.get("risk_level") in EXPLAIN_LEVELS


def build_source_text(report: dict) -> str:
    """The only facts the LLM may use: the engine's own deterministic summary."""
    return str(report.get("summary", ""))


def build_messages(report: dict) -> list[dict]:
    level = report["risk_level"]
    user = f"Risk level: {level}. Engine summary: {build_source_text(report)}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def validate_explanation(text: str, *, level: str, source_text: str) -> tuple[bool, str]:
    """Return (ok, reason). Any failure means the LLM text must be thrown away."""
    text = (text or "").strip()
    if not text:
        return False, "empty"
    if len(text) > MAX_CHARS:
        return False, "too long"
    if not text.startswith(f"Risk level: {level}."):
        return False, "does not start with the engine level"
    if "\n" in text or "**" in text or "`" in text or re.search(r"(?m)^\s*([-*#>]|\d+[.)])\s", text):
        return False, "formatting not allowed"
    if re.search(r"\[[^\]]*\]", text):
        return False, "source tag leaked"
    if len(_sentences(text)) > MAX_SENTENCES:
        return False, "too many sentences"

    for word in _LEVEL_WORDS:
        if word != level and re.search(rf"\b{word}\b", text):
            return False, f"mentions a different level: {word}"
    for m in re.finditer(r"\b(low|moderate|high|critical)\s+risk\b", text.lower()):
        if m.group(1) != level.lower():
            return False, f"mentions a different level: {m.group(1)}"

    src = source_text.lower()
    low = text.lower()
    for pattern in _BANNED:
        if re.search(pattern, low) and not re.search(pattern, src):
            return False, f"speculative or banned wording: {pattern}"

    src_numbers = set(re.findall(r"\d+(?:\.\d+)?", source_text))
    for n in re.findall(r"\d+(?:\.\d+)?", text):
        if n not in src_numbers:
            return False, f"number not in engine text: {n}"
    return True, "ok"