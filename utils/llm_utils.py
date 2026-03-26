"""LLM output utilities.

Handles post-processing of LLM responses — primarily stripping and
logging the <think>...</think> reasoning block produced by DeepSeek-R1
and other chain-of-thought models.
"""

import re
import logging
from datetime import datetime
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# ── Reasoning file logger (deepseek only) ────────────────────────────
_reasoning_log_file: Optional[str] = None
_LOGGABLE_LABELS = {"CustomerReview", "BureauReview"}


def set_reasoning_log_file(path: str) -> None:
    """Enable writing think-block reasoning to a text file."""
    global _reasoning_log_file
    _reasoning_log_file = path


def _write_reasoning_to_file(label: str, content: str) -> None:
    """Append reasoning content to the log file if enabled and label is loggable."""
    if not _reasoning_log_file or label not in _LOGGABLE_LABELS or not content:
        return
    try:
        with open(_reasoning_log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{label}] — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'-'*60}\n")
            f.write(content)
            f.write(f"\n{'='*60}\n\n")
    except Exception as e:
        logger.warning("Failed to write reasoning log: %s", e)


def extract_reasoning(message, label: str = "LLM") -> str:
    """Extract reasoning from AIMessage.additional_kwargs and log it.

    When ChatOllama is used with reasoning=True, the thinking content is
    placed in additional_kwargs["reasoning_content"] rather than in the
    message content.  This function captures that reasoning, logs it to
    the reasoning file (if enabled), and returns only the clean content.

    Also handles the legacy case where <think> tags are inline in content
    (reasoning=None on older Ollama versions).

    Args:
        message: AIMessage from ChatOllama (or plain str for backwards compat).
        label:   Descriptive label for the log entry.

    Returns:
        Clean answer text (str).
    """
    # Backwards compat: if someone passes a plain string, fall through to strip_think
    if isinstance(message, str):
        return strip_think(message, label=label)

    content = message.content or ""
    reasoning = (message.additional_kwargs or {}).get("reasoning_content", "")

    if reasoning:
        reasoning = reasoning.strip()
        logger.debug(
            "\n============================================================\n"
            "[%s — REASONING]\n"
            "------------------------------------------------------------\n"
            "%s\n"
            "============================================================",
            label,
            reasoning,
        )
        _write_reasoning_to_file(label, reasoning)

    # Also handle any inline <think> tags (belt-and-suspenders)
    return strip_think(content, label=label)


def strip_think(text: str, label: str = "LLM") -> str:
    """Strip <think>...</think> block from DeepSeek-R1 / CoT model output.

    The thinking content is logged at DEBUG level so it is visible in logs
    for debugging and learning, but never reaches the final report output.

    Args:
        text:  Raw LLM response, possibly containing a <think> block.
        label: Descriptive label shown in the log line (e.g. "CustomerReview").

    Returns:
        Clean answer text with the think block removed.
    """
    if not text:
        return text

    think_match = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if think_match:
        think_content = think_match.group(1).strip()
        if think_content:
            logger.debug(
                "\n============================================================\n"
                "[%s — THINK BLOCK]\n"
                "------------------------------------------------------------\n"
                "%s\n"
                "============================================================",
                label,
                think_content,
            )
            _write_reasoning_to_file(label, think_content)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    return text


def stream_strip_think(chunks: Iterator[str], label: str = "LLM") -> Iterator[str]:
    """Strip <think> block from a streaming LLM response.

    Buffers the stream until </think> is found (or until it is clear there
    is no think block), logs the thinking content at DEBUG level, then yields
    all subsequent answer chunks transparently.

    Args:
        chunks: Iterator of string chunks from the LLM stream.
        label:  Descriptive label shown in the log line.

    Yields:
        Answer chunks with the think block removed.
    """
    buffer = ""
    think_done = False   # once True we stop buffering and yield directly
    in_think = False

    for chunk in chunks:
        if think_done:
            yield chunk
            continue

        buffer += chunk

        # Detect opening tag
        if not in_think and "<think>" in buffer:
            in_think = True

        # Detect closing tag
        if in_think and "</think>" in buffer:
            think_end = buffer.index("</think>") + len("</think>")
            think_block = buffer[:think_end]
            remainder = buffer[think_end:]

            # Extract and log the think content
            think_match = re.search(r"<think>(.*?)</think>", think_block, flags=re.DOTALL)
            if think_match:
                think_content = think_match.group(1).strip()
                if think_content:
                    logger.debug(
                        "\n============================================================\n"
                        "[%s — THINK BLOCK]\n"
                        "------------------------------------------------------------\n"
                        "%s\n"
                        "============================================================",
                        label,
                        think_content,
                    )

            buffer = ""
            think_done = True
            if remainder:
                yield remainder
            continue

        # No think block at all — if buffer grows large enough, just yield it
        if not in_think and len(buffer) > 200:
            yield buffer
            buffer = ""
            think_done = True

    # Flush any remaining buffer (e.g. model had no think block at all)
    if buffer and not think_done:
        yield buffer
