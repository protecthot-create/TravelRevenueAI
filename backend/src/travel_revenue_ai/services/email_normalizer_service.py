"""Нормализация содержимого email-сообщений без использования AI."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser


class _EmailHtmlTextParser(HTMLParser):
    """Преобразует HTML-письмо в читаемый текст."""

    _BLOCK_TAGS = {
        "address",
        "article",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
    _IGNORED_TAGS = {"head", "script", "style", "title"}

    def __init__(self) -> None:
        """Инициализирует накопитель текстовых фрагментов."""
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Добавляет разделитель для блочных тегов и игнорирует служебные теги."""
        normalized_tag = tag.lower()
        if normalized_tag in self._IGNORED_TAGS:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and normalized_tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Завершает игнорирование служебного тега или добавляет разделитель."""
        normalized_tag = tag.lower()
        if normalized_tag in self._IGNORED_TAGS and self._ignored_depth > 0:
            self._ignored_depth -= 1
        elif self._ignored_depth == 0 and normalized_tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Сохраняет видимый текст HTML-документа."""
        if self._ignored_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        """Возвращает накопленный текст."""
        return "".join(self._parts)


class EmailNormalizerService:
    """Извлекает полезный текст из сырых email-сообщений."""

    MAX_NORMALIZED_LENGTH = 100_000

    _HTML_PATTERN = re.compile(r"<[a-zA-Z!/][^>]*>")
    _WHITESPACE_PATTERN = re.compile(r"\s+")
    _REPLY_CHAIN_PATTERNS = (
        re.compile(
            r"(?im)^\s*on .{1,200}\bwrote:\s*$",
        ),
        re.compile(
            r"(?im)^\s*[-–— ]*original message[-–— ]*\s*$",
        ),
        re.compile(
            r"(?im)^\s*от:\s*.+\n\s*(?:дата|кому|тема):",
        ),
        re.compile(
            r"(?im)^\s*[-–— ]*пересылаемое сообщение[-–— ]*\s*$",
        ),
        re.compile(r"(?m)^\s*>"),
    )
    _SIGNATURE_DELIMITERS = (
        "\n-- \n",
        "\n--\n",
        "\nс уважением,",
        "\nс наилучшими пожеланиями,",
        "\nbest regards,",
        "\nkind regards,",
        "\nregards,",
        "\nthanks,",
    )
    _FOOTER_AND_DISCLAIMER_PATTERNS = (
        re.compile(
            r"(?im)^\s*(?:"
            r"this (?:e-?mail|message).{0,300}(?:confidential|disclaimer)"
            r"|confidentiality notice"
            r"|please consider the environment"
            r"|unsubscribe(?:\s+from.+)?"
            r"|данное (?:электронное )?сообщение.{0,300}"
            r"|конфиденциальн(?:ая|ое|ости)"
            r"|отписаться(?:\s+от.+)?"
            r"|это письмо и любые приложения.{0,300}"
            r")\s*$"
        ),
    )

    def normalize(self, *, subject: str | None, body: str | None) -> str:
        """Формирует единый полезный текст из темы и тела письма.

        Тема добавляется первой. Для тела удаляются HTML-теги, quoted replies,
        цепочки переписки, подписи, footer и disclaimer; затем пробелы
        приводятся к одному виду.
        """
        subject_text = self._clean_fragment(subject or "")
        body_text = self._clean_fragment(body or "")

        result = self._WHITESPACE_PATTERN.sub(
            " ",
            " ".join(fragment for fragment in (subject_text, body_text) if fragment),
        ).strip()
        return result[: self.MAX_NORMALIZED_LENGTH].rstrip()

    def _clean_fragment(self, value: str) -> str:
        """Очищает один текстовый или HTML-фрагмент письма."""
        text = unescape(value).replace("\r\n", "\n").replace("\r", "\n")
        if self._HTML_PATTERN.search(text):
            parser = _EmailHtmlTextParser()
            parser.feed(text)
            parser.close()
            text = parser.get_text()

        text = self._remove_reply_chain(text)
        text = self._remove_signature(text)
        text = self._remove_footer_or_disclaimer(text)
        return text.strip()

    def _remove_reply_chain(self, text: str) -> str:
        """Удаляет начало процитированного ответа и последующую цепочку."""
        positions = [
            match.start()
            for pattern in self._REPLY_CHAIN_PATTERNS
            if (match := pattern.search(text)) is not None
        ]
        return text[: min(positions)] if positions else text

    def _remove_signature(self, text: str) -> str:
        """Отсекает подпись, не удаляя полезный текст перед ней."""
        normalized_text = text.casefold()
        positions = [
            normalized_text.find(delimiter)
            for delimiter in self._SIGNATURE_DELIMITERS
            if normalized_text.find(delimiter) >= 0
        ]
        return text[: min(positions)] if positions else text

    def _remove_footer_or_disclaimer(self, text: str) -> str:
        """Отсекает служебный footer или disclaimer вместе с хвостом письма."""
        positions = [
            match.start()
            for pattern in self._FOOTER_AND_DISCLAIMER_PATTERNS
            if (match := pattern.search(text)) is not None
        ]
        return text[: min(positions)] if positions else text