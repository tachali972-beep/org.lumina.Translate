import sys
import os
from PyQt6.QtGui import QIcon # قم بتغيير PyQt6 إلى مكتبتك الفعلية (PyQt5 أو PySide6)

# هذه الدالة ضرورية للعثور على مسار الشعار بعد تحويل الكود لملف تنفيذي
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fedora Translate Studio - Modern Standalone Linux Desktop Translator & Dictionary
=================================================================================
Target Platform : Fedora Linux (GNOME Wayland, KDE Plasma Wayland, and X11)
Framework       : Python 3.10+ & PyQt6
Engine          : Strictly Google Translate (deep-translator + Google GTX Dictionary RPC)
TTS Engine      : gTTS (Google Text-to-Speech) with Fedora PipeWire/GStreamer/FFmpeg playback
Global Hotkey   : System-wide 'Ctrl + C + C' (within 500ms) via 4-Layer Engine:
                    1. Linux Kernel /dev/input/event* hardware scancode listener (Wayland-native,
                       layout-independent: works in English, Arabic, etc.)
                    2. pynput X11/XWayland keyboard listener (with hardware keycode support)
                    3. X11/Wayland Clipboard & Primary Selection double-event detector
                    4. Optional 1-Copy Instant Translate mode
                  Opens a sleek, borderless, always-on-top Floating Mini-Window.

NOTE: This file is written in 100% pure 7-bit ASCII with QPainter vector icons so it is
completely immune to UTF-8 / Windows-1252 / CP1256 mojibake corruption when copying files.
"""



import glob
import html
import os
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# CRITICAL FEDORA WAYLAND FIX:
# Detect the real session type (Wayland vs X11) FIRST, then default Qt6 to run
# via XWayland ('xcb') on Linux unless the user explicitly overrides it.
# Why? Because native Wayland blocks:
#   1. Unfocused background QClipboard.dataChanged notifications
#   2. Programmatic window positioning (floating_mini.move(cursor_pos))
#   3. Always-on-top window flags (Qt.WindowType.WindowStaysOnTopHint)
# Running via XWayland ('xcb') enables all three on Fedora GNOME Wayland!
# -----------------------------------------------------------------------------
REAL_SESSION_TYPE = (
    os.environ.get("XDG_SESSION_TYPE", "").strip().upper()
    or ("WAYLAND" if os.environ.get("WAYLAND_DISPLAY") else "")
    or ("X11" if os.environ.get("DISPLAY") else "LINUX")
)

if sys.platform.startswith("linux") and os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

import requests
from deep_translator import GoogleTranslator
from gtts import gTTS
from gtts.lang import tts_langs

try:
    from pynput import keyboard as pynput_keyboard

    HAS_PYNPUT = True
except Exception:
    pynput_keyboard = None
    HAS_PYNPUT = False

from PyQt6.QtCore import (
    QObject,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QClipboard,
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# =============================================================================
# 1. PURE QPAINTER VECTOR ICON ENGINE (ZERO EMOJI / ENCODING CORRUPTION)
# =============================================================================
class VectorIcons:
    """
    Draws crisp, high-DPI vector icons using QPainter so buttons and headers
    never rely on system emoji fonts or raw UTF-8 characters.
    """

    @staticmethod
    def _make_canvas(size: int = 18) -> Tuple[QPixmap, QPainter]:
        pix = QPixmap(size * 2, size * 2)
        pix.fill(Qt.GlobalColor.transparent)
        pix.setDevicePixelRatio(2.0)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        return pix, painter

    @classmethod
    def globe(cls, color: str = "#818cf8", size: int = 22) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.8)
        p.setPen(pen)
        r = size - 4
        p.drawEllipse(QRectF(2, 2, r, r))
        p.drawEllipse(QRectF(size * 0.28, 2, size * 0.44, r))
        p.drawLine(QPointF(2, size / 2), QPointF(size - 2, size / 2))
        p.end()
        return QIcon(pix)

    @classmethod
    def speaker(cls, color: str = "#e2e8f0", size: int = 16) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        poly = QPolygonF(
            [
                QPointF(2.5, 6.0),
                QPointF(5.5, 6.0),
                QPointF(9.5, 2.8),
                QPointF(9.5, 13.2),
                QPointF(5.5, 10.0),
                QPointF(2.5, 10.0),
            ]
        )
        p.drawPolygon(poly)
        p.drawArc(QRectF(8.0, 4.5, 4.5, 7.0), -60 * 16, 120 * 16)
        p.drawArc(QRectF(9.0, 2.5, 6.0, 11.0), -60 * 16, 120 * 16)
        p.end()
        return QIcon(pix)

    @classmethod
    def stop(cls, color: str = "#f87171", size: int = 16) -> QIcon:
        pix, p = cls._make_canvas(size)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(3.5, 3.5, 9.0, 9.0), 2.0, 2.0)
        p.end()
        return QIcon(pix)

    @classmethod
    def swap(cls, color: str = "#a5b4fc", size: int = 18) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(3, 6), QPointF(15, 6))
        p.drawLine(QPointF(11.5, 3), QPointF(15, 6))
        p.drawLine(QPointF(11.5, 9), QPointF(15, 6))
        p.drawLine(QPointF(15, 12), QPointF(3, 12))
        p.drawLine(QPointF(6.5, 9), QPointF(3, 12))
        p.drawLine(QPointF(6.5, 15), QPointF(3, 12))
        p.end()
        return QIcon(pix)

    @classmethod
    def copy(cls, color: str = "#e2e8f0", size: int = 16) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(5.5, 5.0, 8.0, 9.0), 1.8, 1.8)
        path = QPainterPath()
        path.moveTo(10.5, 5.0)
        path.lineTo(10.5, 3.2)
        path.lineTo(3.0, 3.2)
        path.lineTo(3.0, 11.5)
        path.lineTo(5.5, 11.5)
        p.drawPath(path)
        p.end()
        return QIcon(pix)

    @classmethod
    def paste(cls, color: str = "#e2e8f0", size: int = 16) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(3.5, 4.0, 9.0, 10.0), 1.8, 1.8)
        p.drawRoundedRect(QRectF(6.0, 2.2, 4.0, 2.5), 1.0, 1.0)
        p.end()
        return QIcon(pix)

    @classmethod
    def clear(cls, color: str = "#e2e8f0", size: int = 16) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(3.0, 4.5), QPointF(13.0, 4.5))
        p.drawLine(QPointF(6.0, 2.8), QPointF(10.0, 2.8))
        p.drawRoundedRect(QRectF(4.5, 4.5, 7.0, 9.5), 1.5, 1.5)
        p.end()
        return QIcon(pix)

    @classmethod
    def book(cls, color: str = "#c084fc", size: int = 16) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(2.5, 3.0, 5.5, 10.5), 1.2, 1.2)
        p.drawRoundedRect(QRectF(8.0, 3.0, 5.5, 10.5), 1.2, 1.2)
        p.end()
        return QIcon(pix)

    @classmethod
    def translate_arrow(cls, color: str = "#ffffff", size: int = 16) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(3.0, 8.0), QPointF(13.0, 8.0))
        p.drawLine(QPointF(9.0, 4.0), QPointF(13.0, 8.0))
        p.drawLine(QPointF(9.0, 12.0), QPointF(13.0, 8.0))
        p.end()
        return QIcon(pix)

    @classmethod
    def close_x(cls, color: str = "#94a3b8", size: int = 14) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(3.5, 3.5), QPointF(size - 3.5, size - 3.5))
        p.drawLine(QPointF(size - 3.5, 3.5), QPointF(3.5, size - 3.5))
        p.end()
        return QIcon(pix)

    @classmethod
    def pin(cls, color: str = "#94a3b8", size: int = 14) -> QIcon:
        pix, p = cls._make_canvas(size)
        pen = QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(QRectF(4.0, 2.5, 6.0, 6.0))
        p.drawLine(QPointF(7.0, 8.5), QPointF(7.0, 12.5))
        p.end()
        return QIcon(pix)

    @classmethod
    def bolt(cls, color: str = "#fbbf24", size: int = 16) -> QIcon:
        pix, p = cls._make_canvas(size)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        poly = QPolygonF(
            [
                QPointF(9.5, 1.5),
                QPointF(3.5, 9.0),
                QPointF(8.0, 9.0),
                QPointF(6.5, 14.5),
                QPointF(12.5, 7.0),
                QPointF(8.0, 7.0),
            ]
        )
        p.drawPolygon(poly)
        p.end()
        return QIcon(pix)


# =============================================================================
# 2. COMPLETE FALLBACK GOOGLE TRANSLATE LANGUAGES (133+ Languages)
# =============================================================================
FALLBACK_GOOGLE_LANGUAGES: Dict[str, str] = {
    "afrikaans": "af",
    "albanian": "sq",
    "amharic": "am",
    "arabic": "ar",
    "armenian": "hy",
    "assamese": "as",
    "aymara": "ay",
    "azerbaijani": "az",
    "bambara": "bm",
    "basque": "eu",
    "belarusian": "be",
    "bengali": "bn",
    "bhojpuri": "bho",
    "bosnian": "bs",
    "bulgarian": "bg",
    "catalan": "ca",
    "cebuano": "ceb",
    "chichewa": "ny",
    "chinese (simplified)": "zh-CN",
    "chinese (traditional)": "zh-TW",
    "corsican": "co",
    "croatian": "hr",
    "czech": "cs",
    "danish": "da",
    "dhivehi": "dv",
    "dogri": "doi",
    "dutch": "nl",
    "english": "en",
    "esperanto": "eo",
    "estonian": "et",
    "ewe": "ee",
    "filipino": "tl",
    "finnish": "fi",
    "french": "fr",
    "frisian": "fy",
    "galician": "gl",
    "georgian": "ka",
    "german": "de",
    "greek": "el",
    "guarani": "gn",
    "gujarati": "gu",
    "haitian creole": "ht",
    "hausa": "ha",
    "hawaiian": "haw",
    "hebrew": "iw",
    "hindi": "hi",
    "hmong": "hmn",
    "hungarian": "hu",
    "icelandic": "is",
    "igbo": "ig",
    "ilocano": "ilo",
    "indonesian": "id",
    "irish": "ga",
    "italian": "it",
    "japanese": "ja",
    "javanese": "jw",
    "kannada": "kn",
    "kazakh": "kk",
    "khmer": "km",
    "kinyarwanda": "rw",
    "konkani": "gom",
    "korean": "ko",
    "krio": "kri",
    "kurdish (kurmanji)": "ku",
    "kurdish (sorani)": "ckb",
    "kyrgyz": "ky",
    "lao": "lo",
    "latin": "la",
    "latvian": "lv",
    "lingala": "ln",
    "lithuanian": "lt",
    "luganda": "lg",
    "luxembourgish": "lb",
    "macedonian": "mk",
    "maithili": "mai",
    "malagasy": "mg",
    "malay": "ms",
    "malayalam": "ml",
    "maltese": "mt",
    "maori": "mi",
    "marathi": "mr",
    "meiteilon (manipuri)": "mni-Mtei",
    "mizo": "lus",
    "mongolian": "mn",
    "myanmar (burmese)": "my",
    "nepali": "ne",
    "norwegian": "no",
    "odia (oriya)": "or",
    "oromo": "om",
    "pashto": "ps",
    "persian": "fa",
    "polish": "pl",
    "portuguese": "pt",
    "punjabi": "pa",
    "quechua": "qu",
    "romanian": "ro",
    "russian": "ru",
    "samoan": "sm",
    "sanskrit": "sa",
    "scots gaelic": "gd",
    "sepedi": "nso",
    "serbian": "sr",
    "sesotho": "st",
    "shona": "sn",
    "sindhi": "sd",
    "sinhala": "si",
    "slovak": "sk",
    "slovenian": "sl",
    "somali": "so",
    "spanish": "es",
    "sundanese": "su",
    "swahili": "sw",
    "swedish": "sv",
    "tajik": "tg",
    "tamil": "ta",
    "tatar": "tt",
    "telugu": "te",
    "thai": "th",
    "tigrinya": "ti",
    "tsonga": "ts",
    "turkish": "tr",
    "turkmen": "tk",
    "twi": "ak",
    "ukrainian": "uk",
    "urdu": "ur",
    "uyghur": "ug",
    "uzbek": "uz",
    "vietnamese": "vi",
    "welsh": "cy",
    "xhosa": "xh",
    "yiddish": "yi",
    "yoruba": "yo",
    "zulu": "zu",
}


# =============================================================================
# 3. DATA STRUCTURES FOR TRANSLATION & DICTIONARY
# =============================================================================
@dataclass
class PartOfSpeechEntry:
    pos: str
    terms: List[str] = field(default_factory=list)
    reverse_map: List[Tuple[str, List[str]]] = field(default_factory=list)


@dataclass
class DefinitionEntry:
    pos: str
    definition: str
    example: Optional[str] = None


@dataclass
class DictionaryResult:
    word: str
    translated_word: str
    source_lang: str
    target_lang: str
    detected_lang: str = ""
    phonetic: str = ""
    pos_entries: List[PartOfSpeechEntry] = field(default_factory=list)
    synonyms_by_pos: Dict[str, List[str]] = field(default_factory=dict)
    alternatives: List[str] = field(default_factory=list)
    definitions: List[DefinitionEntry] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class TranslationResult:
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    detected_lang: str = ""
    phonetic: str = ""
    error: Optional[str] = None


# =============================================================================
# 4. LINUX / FEDORA CLIPBOARD & KEYBOARD INPUT HELPERS
# =============================================================================
def read_linux_clipboard() -> str:
    """
    Robustly reads the clipboard or active primary selection on Fedora (Wayland & X11).
    Checks:
      1. Qt Clipboard (Clipboard mode)
      2. xclip / xsel (XWayland / X11)
      3. wl-paste (Wayland)
      4. Qt Primary Selection (highlighted text on Linux)
    """
    app = QApplication.instance()
    if app is not None:
        cb = app.clipboard()
        if cb is not None:
            text = cb.text(QClipboard.Mode.Clipboard).strip()
            if text:
                return text

    # X11 / XWayland CLI fallback
    if os.environ.get("DISPLAY"):
        if shutil.which("xclip"):
            for sel in ("clipboard", "primary"):
                try:
                    res = subprocess.run(
                        ["xclip", "-o", "-selection", sel],
                        capture_output=True,
                        text=True,
                        timeout=0.5,
                        check=False,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        return res.stdout.strip()
                except Exception:
                    pass
        elif shutil.which("xsel"):
            for flag in ("-ob", "-op"):
                try:
                    res = subprocess.run(
                        ["xsel", flag],
                        capture_output=True,
                        text=True,
                        timeout=0.5,
                        check=False,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        return res.stdout.strip()
                except Exception:
                    pass

    # Wayland CLI fallback
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        for args in (["wl-paste", "--no-newline"], ["wl-paste", "--primary", "--no-newline"]):
            try:
                res = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=0.5,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass

    # Qt Primary Selection (highlighted text in Linux apps)
    if app is not None:
        cb = app.clipboard()
        if cb is not None and cb.supportsSelection():
            text = cb.text(QClipboard.Mode.Selection).strip()
            if text:
                return text

    return ""


def find_readable_keyboard_devices() -> List[str]:
    """
    Finds readable Linux kernel keyboard input devices (/dev/input/event*)
    so we can detect hardware Ctrl+C+C presses on native Wayland across all layouts.
    """
    if not sys.platform.startswith("linux"):
        return []

    candidates: List[str] = []

    for pattern in ("/dev/input/by-path/*-kbd", "/dev/input/by-id/*-kbd"):
        for path in glob.glob(pattern):
            real = os.path.realpath(path)
            if os.access(real, os.R_OK) and real not in candidates:
                candidates.append(real)

    try:
        with open("/proc/bus/input/devices", "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for block in content.split("\n\n"):
            if "EV=120013" in block or "EV=100013" in block or "kbd" in block.lower():
                match = re.search(r"event\d+", block)
                if match:
                    dev_path = f"/dev/input/{match.group(0)}"
                    if os.access(dev_path, os.R_OK) and dev_path not in candidates:
                        candidates.append(dev_path)
    except Exception:
        pass

    return candidates


# =============================================================================
# 5. WORKER THREADS (LANGUAGE FETCHER, TRANSLATOR, DICTIONARY, TTS AUDIO)
# =============================================================================
class LanguageLoaderWorker(QThread):
    """Fetches all supported languages dynamically from Google Translate via deep-translator."""

    languagesLoaded = pyqtSignal(dict)

    def run(self) -> None:
        try:
            langs = GoogleTranslator().get_supported_languages(as_dict=True)
            if isinstance(langs, dict) and len(langs) > 20:
                self.languagesLoaded.emit(langs)
                return
        except Exception:
            pass
        self.languagesLoaded.emit(FALLBACK_GOOGLE_LANGUAGES.copy())


class TranslationWorker(QThread):
    """
    Translates text strictly using Google Translate:
    1. Uses `deep_translator.GoogleTranslator` as the core translation engine.
    2. Queries Google Translate's GTX endpoint for detected source language & phonetics.
    """

    finishedTranslation = pyqtSignal(object)

    def __init__(self, text: str, source_lang: str, target_lang: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.text = text.strip()
        self.source_lang = source_lang
        self.target_lang = target_lang

    def run(self) -> None:
        if not self.text:
            self.finishedTranslation.emit(
                TranslationResult(
                    source_text="",
                    translated_text="",
                    source_lang=self.source_lang,
                    target_lang=self.target_lang,
                )
            )
            return

        detected_lang = self.source_lang if self.source_lang != "auto" else ""
        phonetic = ""
        translated_text = ""

        try:
            translator = GoogleTranslator(source=self.source_lang, target=self.target_lang)
            translated_text = translator.translate(self.text) or ""
        except Exception as exc:
            try:
                translated_text, detected_lang, phonetic = self._fetch_gtx_metadata(include_translation=True)
            except Exception:
                self.finishedTranslation.emit(
                    TranslationResult(
                        source_text=self.text,
                        translated_text="",
                        source_lang=self.source_lang,
                        target_lang=self.target_lang,
                        error=f"Translation error: {exc}",
                    )
                )
                return

        if not detected_lang or not phonetic:
            try:
                _, det, phon = self._fetch_gtx_metadata(include_translation=False)
                if det:
                    detected_lang = det
                if phon:
                    phonetic = phon
            except Exception:
                pass

        self.finishedTranslation.emit(
            TranslationResult(
                source_text=self.text,
                translated_text=translated_text,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                detected_lang=detected_lang or self.source_lang,
                phonetic=phonetic,
            )
        )

    def _fetch_gtx_metadata(self, include_translation: bool = False) -> Tuple[str, str, str]:
        url = "https://translate.googleapis.com/translate_a/single"
        params = [
            ("client", "gtx"),
            ("sl", self.source_lang),
            ("tl", self.target_lang),
            ("dt", "t"),
            ("dt", "rm"),
            ("q", self.text),
        ]
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": "Mozilla/5.0 (X11; Fedora; Linux x86_64)"},
            timeout=6,
        )
        resp.raise_for_status()
        data = resp.json()

        translated_chunks: List[str] = []
        phonetic_chunks: List[str] = []
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
            for seg in data[0]:
                if isinstance(seg, list):
                    if include_translation and len(seg) > 0 and isinstance(seg[0], str):
                        translated_chunks.append(seg[0])
                    if len(seg) > 2 and isinstance(seg[2], str) and seg[2].strip():
                        phonetic_chunks.append(seg[2].strip())
                    elif len(seg) > 3 and isinstance(seg[3], str) and seg[3].strip():
                        phonetic_chunks.append(seg[3].strip())

        detected = ""
        if isinstance(data, list) and len(data) > 2 and isinstance(data[2], str):
            detected = data[2]

        return "".join(translated_chunks), detected, " ".join(phonetic_chunks)


class DictionaryWorker(QThread):
    """
    Fetches single-word translation, parts of speech, alternative meanings,
    reverse translations, synonyms, and definitions strictly from Google Translate.
    """

    finishedLookup = pyqtSignal(object)

    def __init__(self, word: str, source_lang: str, target_lang: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.word = word.strip()
        self.source_lang = source_lang or "auto"
        self.target_lang = target_lang or "en"

    def run(self) -> None:
        if not self.word:
            return

        result = DictionaryResult(
            word=self.word,
            translated_word="",
            source_lang=self.source_lang,
            target_lang=self.target_lang,
        )

        try:
            gt = GoogleTranslator(source=self.source_lang, target=self.target_lang)
            primary = gt.translate(self.word)
            if primary:
                result.translated_word = primary.strip()
        except Exception as exc:
            result.error = str(exc)

        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = [
                ("client", "gtx"),
                ("sl", self.source_lang),
                ("tl", self.target_lang),
                ("hl", self.target_lang),
                ("dt", "t"),
                ("dt", "bd"),
                ("dt", "at"),
                ("dt", "ss"),
                ("dt", "md"),
                ("dt", "ex"),
                ("dt", "rm"),
                ("q", self.word),
            ]
            resp = requests.get(
                url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (X11; Fedora; Linux x86_64)"},
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                trans_parts: List[str] = []
                phon_parts: List[str] = []
                for item in data[0]:
                    if isinstance(item, list):
                        if len(item) > 0 and isinstance(item[0], str):
                            trans_parts.append(item[0])
                        if len(item) > 3 and isinstance(item[3], str) and item[3].strip():
                            phon_parts.append(item[3].strip())
                        elif len(item) > 2 and isinstance(item[2], str) and item[2].strip():
                            phon_parts.append(item[2].strip())
                if not result.translated_word and trans_parts:
                    result.translated_word = "".join(trans_parts).strip()
                if phon_parts:
                    result.phonetic = " / ".join(dict.fromkeys(phon_parts))

            if isinstance(data, list) and len(data) > 2 and isinstance(data[2], str):
                result.detected_lang = data[2]

            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                for entry in data[1]:
                    if not isinstance(entry, list) or len(entry) < 2:
                        continue
                    pos_name = str(entry[0]).strip() if entry[0] else "general"
                    terms = [str(t) for t in entry[1] if isinstance(t, str)] if isinstance(entry[1], list) else []
                    reverse_map: List[Tuple[str, List[str]]] = []
                    if len(entry) > 2 and isinstance(entry[2], list):
                        for rev in entry[2]:
                            if isinstance(rev, list) and len(rev) >= 2:
                                target_term = str(rev[0])
                                rev_syns = [str(s) for s in rev[1] if isinstance(s, str)] if isinstance(rev[1], list) else []
                                reverse_map.append((target_term, rev_syns[:6]))
                    result.pos_entries.append(
                        PartOfSpeechEntry(pos=pos_name, terms=terms[:10], reverse_map=reverse_map[:8])
                    )

            if isinstance(data, list) and len(data) > 5 and isinstance(data[5], list):
                seen_alts = {result.translated_word.lower()} if result.translated_word else set()
                for alt_group in data[5]:
                    if isinstance(alt_group, list) and len(alt_group) > 2 and isinstance(alt_group[2], list):
                        for cand in alt_group[2]:
                            if isinstance(cand, list) and len(cand) > 0 and isinstance(cand[0], str):
                                word_cand = cand[0].strip()
                                if word_cand and word_cand.lower() not in seen_alts:
                                    seen_alts.add(word_cand.lower())
                                    result.alternatives.append(word_cand)

            if isinstance(data, list) and len(data) > 11 and isinstance(data[11], list):
                for syn_block in data[11]:
                    if isinstance(syn_block, list) and len(syn_block) >= 2:
                        pos_label = str(syn_block[0]).strip() or "synonyms"
                        collected: List[str] = result.synonyms_by_pos.setdefault(pos_label, [])
                        if isinstance(syn_block[1], list):
                            for syn_group in syn_block[1]:
                                if isinstance(syn_group, list) and len(syn_group) > 0 and isinstance(syn_group[0], list):
                                    for s in syn_group[0]:
                                        if isinstance(s, str) and s not in collected:
                                            collected.append(s)

            if isinstance(data, list) and len(data) > 12 and isinstance(data[12], list):
                for def_block in data[12]:
                    if isinstance(def_block, list) and len(def_block) >= 2:
                        pos_label = str(def_block[0]).strip() or "definition"
                        if isinstance(def_block[1], list):
                            for d_item in def_block[1][:3]:
                                if isinstance(d_item, list) and len(d_item) >= 1 and isinstance(d_item[0], str):
                                    example_str = str(d_item[2]) if len(d_item) > 2 and isinstance(d_item[2], str) else None
                                    result.definitions.append(
                                        DefinitionEntry(
                                            pos=pos_label,
                                            definition=d_item[0],
                                            example=example_str,
                                        )
                                    )

            result.error = None
        except Exception as exc:
            if not result.translated_word:
                result.error = f"Dictionary lookup failed: {exc}"

        self.finishedLookup.emit(result)


class TTSWorker(QThread):
    """
    Generates natural speech via Google Text-to-Speech (gTTS) and plays it cleanly
    on Fedora Linux (supporting PipeWire / PulseAudio / FFmpeg / MPV / GStreamer / espeak-ng).
    """

    playbackStarted = pyqtSignal()
    playbackFinished = pyqtSignal()
    playbackError = pyqtSignal(str)

    GTTS_LANG_MAP: Dict[str, str] = {
        "iw": "iw",
        "he": "iw",
        "jw": "jw",
        "zh-CN": "zh-CN",
        "zh-TW": "zh-TW",
        "fil": "tl",
        "mni-Mtei": "bn",
        "ckb": "ar",
    }

    def __init__(self, text: str, lang_code: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.text = text.strip()
        self.lang_code = lang_code.strip() if lang_code else "en"
        self._stop_requested = False
        self._proc: Optional[subprocess.Popen] = None

    def stop(self) -> None:
        self._stop_requested = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _resolve_gtts_lang(self, code: str) -> str:
        if not code or code == "auto":
            try:
                resp = requests.get(
                    "https://translate.googleapis.com/translate_a/single",
                    params=[("client", "gtx"), ("sl", "auto"), ("tl", "en"), ("dt", "t"), ("q", self.text[:160])],
                    timeout=4,
                )
                data = resp.json()
                if isinstance(data, list) and len(data) > 2 and isinstance(data[2], str) and data[2]:
                    code = data[2]
                else:
                    code = "en"
            except Exception:
                code = "en"

        code = self.GTTS_LANG_MAP.get(code, code)
        try:
            supported = tts_langs()
            if code in supported:
                return code
            lower_map = {k.lower(): k for k in supported.keys()}
            if code.lower() in lower_map:
                return lower_map[code.lower()]
            base = code.split("-")[0].lower()
            if base in lower_map:
                return lower_map[base]
        except Exception:
            pass
        return "en"

    def run(self) -> None:
        if not self.text:
            self.playbackFinished.emit()
            return

        self.playbackStarted.emit()
        tmp_mp3: Optional[str] = None
        try:
            lang = self._resolve_gtts_lang(self.lang_code)
            with tempfile.NamedTemporaryFile(prefix="fedora_tts_", suffix=".mp3", delete=False) as tf:
                tmp_mp3 = tf.name

            tts = gTTS(text=self.text, lang=lang, slow=False)
            tts.save(tmp_mp3)

            if self._stop_requested:
                self.playbackFinished.emit()
                return

            played = self._play_audio_file_linux(tmp_mp3)
            if not played and not self._stop_requested:
                if not self._fallback_offline_tts(self.text, lang):
                    self.playbackError.emit(
                        "No audio player found. Install 'ffmpeg-free' or 'mpv' or 'mpg123' on Fedora."
                    )
        except Exception as exc:
            if not self._stop_requested:
                if not self._fallback_offline_tts(self.text, self.lang_code):
                    self.playbackError.emit(f"TTS Error: {exc}")
        finally:
            if tmp_mp3 and os.path.exists(tmp_mp3):
                try:
                    os.remove(tmp_mp3)
                except Exception:
                    pass
            self.playbackFinished.emit()

    def _play_audio_file_linux(self, filepath: str) -> bool:
        candidates: List[List[str]] = [
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", filepath],
            ["mpv", "--no-video", "--really-quiet", filepath],
            ["gst-play-1.0", "--quiet", filepath],
            ["mpg123", "-q", filepath],
            ["cvlc", "--play-and-exit", "--quiet", filepath],
            ["play", "-q", filepath],
        ]
        for cmd in candidates:
            if shutil.which(cmd[0]):
                try:
                    self._proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    while self._proc.poll() is None:
                        if self._stop_requested:
                            self._proc.terminate()
                            return True
                        self.msleep(40)
                    if self._proc.returncode == 0 or self._stop_requested:
                        return True
                except Exception:
                    continue
        return False

    def _fallback_offline_tts(self, text: str, lang: str) -> bool:
        base_lang = (lang or "en").split("-")[0]
        for cmd in (["espeak-ng", "-v", base_lang, text], ["spd-say", "-w", "-l", base_lang, text]):
            if shutil.which(cmd[0]):
                try:
                    self._proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    while self._proc.poll() is None:
                        if self._stop_requested:
                            self._proc.terminate()
                            return True
                        self.msleep(40)
                    return True
                except Exception:
                    continue
        return False


# =============================================================================
# 6. 4-LAYER GLOBAL 'Ctrl + C + C' HOTKEY ENGINE (FEDORA WAYLAND + X11)
# =============================================================================
class GlobalDoubleCopyMonitor(QObject):
    """
    Bulletproof 'Ctrl + C + C' (within 500ms) detector for Fedora Wayland & X11:
      Layer 1: Linux Kernel /dev/input/event* reader (EV_KEY scancode 46 = KEY_C,
               scancodes 29/97 = Ctrl). Works globally across ALL native Wayland
               and X11 apps and ALL keyboard layouts (English, Arabic, etc.)!
      Layer 2: `pynput` X11/XWayland listener with hardware scan-code (54) & keysym support.
      Layer 3: `xinput test-xi2 --root` raw XInput2 key listener (captures XWayland keys).
      Layer 4: Qt QClipboard (`changed` / `dataChanged` / `selectionChanged`) monitor +
               optional "Single Ctrl+C Instant Popup" mode.
    """

    doubleCopyTriggered = pyqtSignal()
    statusChanged = pyqtSignal(str, bool)  # (status_text, has_wayland_evdev)

    _internalTrigger = pyqtSignal()

    INTERVAL_S = 0.50
    MIN_INTERVAL_S = 0.04

    # Linux kernel input-event-codes.h constants
    EV_KEY = 0x01
    KEY_LEFTCTRL = 29
    KEY_RIGHTCTRL = 97
    KEY_C = 46
    EVENT_STRUCT = struct.Struct("llHHi")

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.enabled: bool = True
        self.single_copy_mode: bool = False

        self._ctrl_pressed_pynput: bool = False
        self._last_c_time: float = 0.0
        self._last_clip_time: float = 0.0
        self._last_fire_time: float = 0.0
        self._ignore_until: float = 0.0
        self._lock = threading.Lock()

        self._stop_flag = False
        self._pynput_listener: Optional[object] = None
        self._evdev_thread: Optional[threading.Thread] = None
        self._xi2_proc: Optional[subprocess.Popen] = None
        self.has_evdev_access: bool = False

        self._internalTrigger.connect(self._on_triggered_main_thread)

        app = QApplication.instance()
        if app is not None and app.clipboard() is not None:
            cb = app.clipboard()
            cb.dataChanged.connect(self._on_clipboard_Activity)
            cb.changed.connect(self._on_clipboard_mode_changed)

    def mark_internal_copy(self) -> None:
        """Prevents the app's own Copy buttons from triggering the popup."""
        self._ignore_until = time.monotonic() + 0.85

    def start(self) -> None:
        self._stop_flag = False
        self._start_evdev_listener()
        self._start_pynput_listener()
        self._start_xi2_listener()
        self._emit_status()

    def restart_evdev(self) -> bool:
        """Re-scans /dev/input/event* after the user grants ACL permissions via pkexec."""
        self._start_evdev_listener()
        self._emit_status()
        return self.has_evdev_access

    def stop(self) -> None:
        self._stop_flag = True
        if self._pynput_listener is not None:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
            self._pynput_listener = None
        if self._xi2_proc is not None and self._xi2_proc.poll() is None:
            try:
                self._xi2_proc.terminate()
            except Exception:
                pass
            self._xi2_proc = None

    def _emit_status(self) -> None:
        if self.has_evdev_access:
            self.statusChanged.emit("Wayland/X11 Global Key Hook: Active", True)
        elif REAL_SESSION_TYPE == "WAYLAND":
            self.statusChanged.emit("Wayland Clipboard Hook (Click to Enable Hardware Key Hook)", False)
        else:
            self.statusChanged.emit("X11 Global Key Hook: Active", True)

    def _record_c_press(self) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if now < self._ignore_until:
            return
        with self._lock:
            delta = now - self._last_c_time
            if self.MIN_INTERVAL_S <= delta <= self.INTERVAL_S:
                self._last_c_time = 0.0
                if now - self._last_fire_time > 0.40:
                    self._last_fire_time = now
                    self._internalTrigger.emit()
            else:
                self._last_c_time = now

    # --- Layer 1: Linux Kernel /dev/input/event* Reader (Wayland Native) ---
    def _start_evdev_listener(self) -> None:
        devices = find_readable_keyboard_devices()
        if not devices:
            self.has_evdev_access = False
            return
        self.has_evdev_access = True
        if self._evdev_thread is not None and self._evdev_thread.is_alive():
            return
        self._evdev_thread = threading.Thread(
            target=self._evdev_loop,
            args=(devices,),
            daemon=True,
        )
        self._evdev_thread.start()

    def _evdev_loop(self, device_paths: List[str]) -> None:
        fds: List[int] = []
        for path in device_paths:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                fds.append(fd)
            except Exception:
                continue

        if not fds:
            self.has_evdev_access = False
            return

        ctrl_down = False
        event_size = self.EVENT_STRUCT.size

        try:
            while not self._stop_flag:
                rlist, _, _ = select.select(fds, [], [], 0.5)
                for fd in rlist:
                    try:
                        data = os.read(fd, event_size * 16)
                    except OSError:
                        continue
                    if not data:
                        continue
                    for offset in range(0, len(data) - event_size + 1, event_size):
                        _, _, ev_type, code, value = self.EVENT_STRUCT.unpack_from(data, offset)
                        if ev_type != self.EV_KEY:
                            continue
                        if code in (self.KEY_LEFTCTRL, self.KEY_RIGHTCTRL):
                            ctrl_down = value in (1, 2)
                        elif code == self.KEY_C and value == 1 and ctrl_down:
                            self._record_c_press()
        finally:
            for fd in fds:
                try:
                    os.close(fd)
                except Exception:
                    pass

    # --- Layer 2: pynput Listener (with Arabic/non-Latin & X11 scan code support) ---
    def _start_pynput_listener(self) -> None:
        if not HAS_PYNPUT or pynput_keyboard is None:
            return
        try:
            self._pynput_listener = pynput_keyboard.Listener(
                on_press=self._on_pynput_press,
                on_release=self._on_pynput_release,
            )
            self._pynput_listener.daemon = True
            self._pynput_listener.start()
        except Exception:
            self._pynput_listener = None

    def _is_pynput_ctrl(self, key: object) -> bool:
        if not HAS_PYNPUT or pynput_keyboard is None:
            return False
        return key in {
            getattr(pynput_keyboard.Key, "ctrl", None),
            getattr(pynput_keyboard.Key, "ctrl_l", None),
            getattr(pynput_keyboard.Key, "ctrl_r", None),
        }

    def _is_pynput_c(self, key: object) -> bool:
        # 1. Check X11 hardware keycode (_scan == 54 is physical 'C' key in any layout)
        if getattr(key, "_scan", None) == 54:
            return True
        # 2. Check character (English 'c'/'C', Ctrl+C '\x03', or Arabic '\u0626' on C key)
        char = getattr(key, "char", None)
        if char in ("c", "C", "\x03", "\u0626"):
            return True
        # 3. Check virtual key / keysym
        vk = getattr(key, "vk", None)
        if vk in (67, 99, 0x1000626):
            return True
        return False

    def _on_pynput_press(self, key: object) -> None:
        if self._is_pynput_ctrl(key):
            self._ctrl_pressed_pynput = True
            return
        if self._ctrl_pressed_pynput and self._is_pynput_c(key):
            self._record_c_press()

    def _on_pynput_release(self, key: object) -> None:
        if self._is_pynput_ctrl(key):
            self._ctrl_pressed_pynput = False

    # --- Layer 3: XInput2 Raw Key Listener (`xinput test-xi2 --root`) ---
    def _start_xi2_listener(self) -> None:
        if not sys.platform.startswith("linux") or not shutil.which("xinput"):
            return
        threading.Thread(target=self._xi2_loop, daemon=True).start()

    def _xi2_loop(self) -> None:
        try:
            self._xi2_proc = subprocess.Popen(
                ["xinput", "test-xi2", "--root"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except Exception:
            return

        ctrl_down = False
        current_event = ""
        if self._xi2_proc.stdout is None:
            return

        for line in self._xi2_proc.stdout:
            if self._stop_flag:
                break
            stripped = line.strip()
            if stripped.startswith("EVENT type"):
                current_event = stripped
            elif stripped.startswith("detail:"):
                parts = stripped.split()
                if len(parts) < 2 or not parts[1].isdigit():
                    continue
                keycode = int(parts[1])
                if "(RawKeyPress)" in current_event:
                    if keycode in (37, 105):
                        ctrl_down = True
                    elif keycode == 54 and ctrl_down:
                        self._record_c_press()
                elif "(RawKeyRelease)" in current_event:
                    if keycode in (37, 105):
                        ctrl_down = False

    # --- Layer 4: Clipboard Event Detector ---
    def _on_clipboard_mode_changed(self, mode: QClipboard.Mode) -> None:
        if mode == QClipboard.Mode.Clipboard:
            self._on_clipboard_Activity()

    def _on_clipboard_Activity(self) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if now < self._ignore_until:
            return
        with self._lock:
            if self.single_copy_mode:
                if now - self._last_fire_time > 0.45:
                    self._last_fire_time = now
                    self._internalTrigger.emit()
                return

            delta = now - self._last_clip_time
            if self.MIN_INTERVAL_S <= delta <= self.INTERVAL_S:
                self._last_clip_time = 0.0
                if now - self._last_fire_time > 0.40:
                    self._last_fire_time = now
                    self._internalTrigger.emit()
            else:
                self._last_clip_time = now

    def _on_triggered_main_thread(self) -> None:
        self.doubleCopyTriggered.emit()


# =============================================================================
# 7. CUSTOM TEXT EDIT WITH DOUBLE-CLICK WORD DICTIONARY LOOKUP
# =============================================================================
class DictionaryTextEdit(QTextEdit):
    """
    Custom QTextEdit that intercepts mouse double-clicks on any word, highlights it,
    and emits `wordDoubleClicked(word, is_source_editor, global_cursor_pos)`.
    """

    wordDoubleClicked = pyqtSignal(str, bool, QPoint)

    WORD_CLEAN_RE = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)

    def __init__(self, is_source: bool = True, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.is_source = is_source

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return

        cursor = self.cursorForPosition(event.pos())
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        raw_word = cursor.selectedText().strip()
        cleaned_word = self.WORD_CLEAN_RE.sub("", raw_word)

        if cleaned_word and len(cleaned_word) <= 64:
            self.setTextCursor(cursor)
            global_pos = self.mapToGlobal(event.pos())
            self.wordDoubleClicked.emit(cleaned_word, self.is_source, global_pos)


# =============================================================================
# 8. DICTIONARY HTML RENDERER & FLOATING POPUP CARD
# =============================================================================
def format_dictionary_html(res: DictionaryResult, lang_code_to_name: Dict[str, str]) -> str:
    """Renders a clean, modern HTML view for a DictionaryResult using pure ASCII HTML entities."""
    if res.error and not res.translated_word:
        return f"""
        <div style='color:#f87171; padding:10px;'>
            <b>Dictionary Lookup Error</b><br>{html.escape(res.error)}
        </div>
        """

    src_code = res.detected_lang or res.source_lang
    src_name = lang_code_to_name.get(src_code, src_code.upper()).title()
    tgt_name = lang_code_to_name.get(res.target_lang, res.target_lang.upper()).title()

    phonetic_html = (
        f"<div style='color:#94a3b8; font-size:12px; margin-top:2px;'>/{html.escape(res.phonetic)}/</div>"
        if res.phonetic
        else ""
    )

    parts: List[str] = [
        f"""
        <div style='background-color:#1e2235; border-radius:10px; padding:12px; margin-bottom:10px;'>
            <div style='font-size:11px; color:#818cf8; font-weight:600; text-transform:uppercase;'>
                {html.escape(src_name)} &rarr; {html.escape(tgt_name)}
            </div>
            <div style='font-size:20px; font-weight:700; color:#f8fafc; margin-top:3px;'>
                {html.escape(res.word)}
            </div>
            {phonetic_html}
            <div style='font-size:18px; font-weight:700; color:#38bdf8; margin-top:6px;'>
                {html.escape(res.translated_word or "-")}
            </div>
        </div>
        """
    ]

    if res.alternatives:
        chips = ", ".join(html.escape(a) for a in res.alternatives[:8])
        parts.append(
            f"""
            <div style='margin-bottom:10px;'>
                <div style='font-size:11px; font-weight:700; color:#94a3b8; text-transform:uppercase; margin-bottom:4px;'>
                    Alternative Translations
                </div>
                <div style='color:#e2e8f0; font-size:13px; line-height:1.5;'>{chips}</div>
            </div>
            """
        )

    if res.pos_entries:
        for entry in res.pos_entries:
            pos_badge = html.escape(entry.pos.upper())
            parts.append(
                f"""
                <div style='margin-top:8px; margin-bottom:8px;'>
                    <div style='color:#a5b4fc; font-size:11px; font-weight:700; letter-spacing:0.6px; margin-bottom:4px;'>
                        &#9679; {pos_badge}
                    </div>
                """
            )
            if entry.reverse_map:
                for target_term, rev_syns in entry.reverse_map[:6]:
                    syns_str = ", ".join(html.escape(s) for s in rev_syns)
                    parts.append(
                        f"""
                        <div style='margin-left:8px; margin-bottom:4px; font-size:13px;'>
                            <b style='color:#f1f5f9;'>{html.escape(target_term)}</b>
                            <span style='color:#64748b;'> &mdash; </span>
                            <span style='color:#94a3b8;'>{syns_str}</span>
                        </div>
                        """
                    )
            elif entry.terms:
                terms_str = ", ".join(html.escape(t) for t in entry.terms)
                parts.append(
                    f"<div style='margin-left:8px; color:#cbd5e1; font-size:13px;'>{terms_str}</div>"
                )
            parts.append("</div>")

    if res.synonyms_by_pos:
        parts.append(
            """
            <div style='margin-top:10px; margin-bottom:4px; font-size:11px; font-weight:700;
                        color:#34d399; text-transform:uppercase;'>
                Synonyms
            </div>
            """
        )
        for pos_label, syns in res.synonyms_by_pos.items():
            if not syns:
                continue
            syn_list = ", ".join(html.escape(s) for s in syns[:10])
            parts.append(
                f"""
                <div style='margin-left:6px; margin-bottom:5px; font-size:12px;'>
                    <span style='color:#6ee7b7; font-style:italic;'>({html.escape(pos_label)})</span>
                    <span style='color:#cbd5e1;'> {syn_list}</span>
                </div>
                """
            )

    if res.definitions:
        parts.append(
            """
            <div style='margin-top:10px; margin-bottom:4px; font-size:11px; font-weight:700;
                        color:#fbbf24; text-transform:uppercase;'>
                Definitions &amp; Usage
            </div>
            """
        )
        for d in res.definitions[:4]:
            ex_html = (
                f"<br><span style='color:#94a3b8; font-style:italic;'>&ldquo;{html.escape(d.example)}&rdquo;</span>"
                if d.example
                else ""
            )
            parts.append(
                f"""
                <div style='margin-left:6px; margin-bottom:6px; font-size:12px; color:#e2e8f0;'>
                    <span style='color:#fcd34d; font-weight:600;'>[{html.escape(d.pos)}]</span>
                    {html.escape(d.definition)}
                    {ex_html}
                </div>
                """
            )

    if not res.pos_entries and not res.alternatives and not res.synonyms_by_pos and not res.definitions:
        parts.append(
            "<div style='color:#64748b; font-size:12px; margin-top:6px;'>"
            "Single-word translation completed."
            "</div>"
        )

    return "".join(parts)


class FloatingDictionaryPopup(QWidget):
    """Floating popup card that appears near a double-clicked word."""

    pronounceRequested = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(390, 340)

        self._current_word = ""
        self._current_lang = "en"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self.card = QFrame(self)
        self.card.setObjectName("PopupCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(VectorIcons.book("#a5b4fc", 16).pixmap(16, 16))
        header.addWidget(icon_lbl)

        self.title_lbl = QLabel("Word Dictionary")
        self.title_lbl.setStyleSheet("color:#a5b4fc; font-weight:700; font-size:12px;")
        header.addWidget(self.title_lbl)
        header.addStretch()

        self.speak_btn = QPushButton("Listen")
        self.speak_btn.setIcon(VectorIcons.speaker("#e2e8f0", 14))
        self.speak_btn.setObjectName("MiniActionBtn")
        self.speak_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.speak_btn.clicked.connect(self._on_speak)
        header.addWidget(self.speak_btn)

        self.close_btn = QPushButton()
        self.close_btn.setIcon(VectorIcons.close_x("#94a3b8", 14))
        self.close_btn.setObjectName("IconCloseBtn")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.hide)
        header.addWidget(self.close_btn)

        card_layout.addLayout(header)

        self.browser = QTextEdit()
        self.browser.setReadOnly(True)
        self.browser.setObjectName("DictPopupView")
        card_layout.addWidget(self.browser)

        outer.addWidget(self.card)

    def show_loading(self, word: str, global_pos: QPoint) -> None:
        self._current_word = word
        self.browser.setHtml(
            f"<div style='color:#94a3b8; padding:12px;'>Looking up <b>{html.escape(word)}</b> in Google Translate Dictionary&hellip;</div>"
        )
        self._position_near(global_pos)
        self.show()
        self.raise_()

    def show_result(self, res: DictionaryResult, lang_code_to_name: Dict[str, str]) -> None:
        self._current_word = res.word
        self._current_lang = res.detected_lang or res.source_lang or "en"
        self.browser.setHtml(format_dictionary_html(res, lang_code_to_name))

    def _on_speak(self) -> None:
        if self._current_word:
            self.pronounceRequested.emit(self._current_word, self._current_lang)

    def _position_near(self, pos: QPoint) -> None:
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is None:
            self.move(pos + QPoint(12, 16))
            return
        avail = screen.availableGeometry()
        x = min(max(avail.left() + 10, pos.x() - 40), avail.right() - self.width() - 10)
        y = pos.y() + 20
        if y + self.height() > avail.bottom() - 10:
            y = max(avail.top() + 10, pos.y() - self.height() - 15)
        self.move(x, y)


# =============================================================================
# 9. SLEEK BORDERLESS 'ALWAYS-ON-TOP' FLOATING MINI-WINDOW (Ctrl + C + C)
# =============================================================================
class FloatingMiniTranslator(QWidget):
    """
    Borderless, always-on-top floating mini-window triggered when the user presses
    'Ctrl + C + C' within 500ms anywhere on Fedora Linux.
    Shows & activates FIRST so Wayland compositors immediately grant clipboard focus,
    then reads and translates the clipboard text.
    """

    openInMainRequested = pyqtSignal(str, str)
    speakRequested = pyqtSignal(str, str)
    wordLookupRequested = pyqtSignal(str, bool, QPoint)

    def __init__(
        self,
        lang_name_to_code: Dict[str, str],
        lang_code_to_name: Dict[str, str],
        mark_internal_copy_cb: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(480, 320)

        self.lang_name_to_code = lang_name_to_code
        self.lang_code_to_name = lang_code_to_name
        self.mark_internal_copy_cb = mark_internal_copy_cb

        self._drag_offset: Optional[QPoint] = None
        self._pinned: bool = False
        self._source_text: str = ""
        self._translated_text: str = ""
        self._detected_source_lang: str = "auto"
        self._worker: Optional[TranslationWorker] = None

        self._build_ui()

        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.activated.connect(self.hide)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        self.container = QFrame(self)
        self.container.setObjectName("FloatingMiniContainer")

        shadow = QGraphicsDropShadowEffect(self.container)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.container.setGraphicsEffect(shadow)

        vbox = QVBoxLayout(self.container)
        vbox.setContentsMargins(16, 12, 16, 14)
        vbox.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        bolt_lbl = QLabel()
        bolt_lbl.setPixmap(VectorIcons.bolt("#818cf8", 16).pixmap(16, 16))
        top_bar.addWidget(bolt_lbl)

        badge = QLabel("Quick Translate (Ctrl+C+C)")
        badge.setStyleSheet("color:#818cf8; font-weight:700; font-size:12px;")
        top_bar.addWidget(badge)

        top_bar.addStretch()

        self.target_combo = QComboBox()
        self.target_combo.setObjectName("MiniCombo")
        self.target_combo.setMinimumWidth(145)
        self.populate_languages(self.lang_name_to_code, default_code="ar")
        self.target_combo.currentIndexChanged.connect(self._retranslate_current)
        top_bar.addWidget(self.target_combo)

        self.pin_btn = QPushButton()
        self.pin_btn.setIcon(VectorIcons.pin("#94a3b8", 14))
        self.pin_btn.setObjectName("IconCloseBtn")
        self.pin_btn.setToolTip("Pin window on top")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setFixedSize(26, 26)
        self.pin_btn.clicked.connect(self._toggle_pin)
        top_bar.addWidget(self.pin_btn)

        close_btn = QPushButton()
        close_btn.setIcon(VectorIcons.close_x("#94a3b8", 14))
        close_btn.setObjectName("IconCloseBtn")
        close_btn.setToolTip("Close (Esc)")
        close_btn.setFixedSize(26, 26)
        close_btn.clicked.connect(self.hide)
        top_bar.addWidget(close_btn)

        vbox.addLayout(top_bar)

        self.src_preview = QLabel("")
        self.src_preview.setWordWrap(True)
        self.src_preview.setMaximumHeight(44)
        self.src_preview.setStyleSheet(
            "color:#94a3b8; font-size:12px; background-color:#151824; border-radius:6px; padding:6px;"
        )
        vbox.addWidget(self.src_preview)

        self.output_edit = DictionaryTextEdit(is_source=False, parent=self.container)
        self.output_edit.setReadOnly(True)
        self.output_edit.setObjectName("MiniOutputEdit")
        self.output_edit.setPlaceholderText("Translating clipboard text...")
        self.output_edit.wordDoubleClicked.connect(self.wordLookupRequested.emit)
        vbox.addWidget(self.output_edit, stretch=1)

        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(6)

        self.status_lbl = QLabel("Double-click any word for dictionary")
        self.status_lbl.setStyleSheet("color:#64748b; font-size:11px;")
        bottom_bar.addWidget(self.status_lbl)

        bottom_bar.addStretch()

        self.listen_src_btn = QPushButton("Source")
        self.listen_src_btn.setIcon(VectorIcons.speaker("#cbd5e1", 14))
        self.listen_src_btn.setObjectName("MiniActionBtn")
        self.listen_src_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.listen_src_btn.clicked.connect(
            lambda: self.speakRequested.emit(self._source_text, self._detected_source_lang)
        )
        bottom_bar.addWidget(self.listen_src_btn)

        self.listen_tgt_btn = QPushButton("Listen")
        self.listen_tgt_btn.setIcon(VectorIcons.speaker("#cbd5e1", 14))
        self.listen_tgt_btn.setObjectName("MiniActionBtn")
        self.listen_tgt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.listen_tgt_btn.clicked.connect(
            lambda: self.speakRequested.emit(self._translated_text, self.current_target_code())
        )
        bottom_bar.addWidget(self.listen_tgt_btn)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setIcon(VectorIcons.copy("#cbd5e1", 14))
        self.copy_btn.setObjectName("MiniActionBtn")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_translation)
        bottom_bar.addWidget(self.copy_btn)

        self.expand_btn = QPushButton("Open Studio")
        self.expand_btn.setObjectName("MiniPrimaryBtn")
        self.expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_btn.clicked.connect(self._open_in_main)
        bottom_bar.addWidget(self.expand_btn)

        vbox.addLayout(bottom_bar)
        root_layout.addWidget(self.container)

    def populate_languages(self, lang_name_to_code: Dict[str, str], default_code: str = "ar") -> None:
        current_code = self.current_target_code() or default_code
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        selected_idx = 0
        for idx, (name, code) in enumerate(sorted(lang_name_to_code.items())):
            display = f"{name.title()} ({code})"
            self.target_combo.addItem(display, code)
            if code.lower() == current_code.lower():
                selected_idx = idx
        self.target_combo.setCurrentIndex(selected_idx)
        self.target_combo.blockSignals(False)

    def current_target_code(self) -> str:
        return self.target_combo.currentData() or "ar"

    def popup_and_grab_clipboard(self, target_code: Optional[str] = None, explicit_text: Optional[str] = None) -> None:
        if target_code:
            idx = self.target_combo.findData(target_code)
            if idx >= 0:
                self.target_combo.blockSignals(True)
                self.target_combo.setCurrentIndex(idx)
                self.target_combo.blockSignals(False)

        self._position_near_cursor()
        self.show()
        self.raise_()
        self.activateWindow()

        if explicit_text and explicit_text.strip():
            self._apply_source_and_translate(explicit_text.strip())
            return

        text_now = read_linux_clipboard()
        if text_now:
            self._apply_source_and_translate(text_now)
        else:
            self.src_preview.setText("Reading Linux clipboard...")
            self.output_edit.setPlainText("Waiting for clipboard text...")

        QTimer.singleShot(70, self._retry_clipboard_grab)
        QTimer.singleShot(160, self._retry_clipboard_grab)

    def _retry_clipboard_grab(self) -> None:
        text = read_linux_clipboard()
        if text and text != self._source_text:
            self._apply_source_and_translate(text)

    def _apply_source_and_translate(self, text: str) -> None:
        self._source_text = text.strip()
        if not self._source_text:
            return
        preview = self._source_text.replace("\n", " ")
        if len(preview) > 110:
            preview = preview[:110] + "..."
        self.src_preview.setText(preview)
        self.output_edit.setPlainText("Translating with Google Translate...")
        self.status_lbl.setText("Fetching translation...")
        self._retranslate_current()

    def _retranslate_current(self) -> None:
        if not self._source_text:
            return
        if self._worker and self._worker.isRunning():
            self._worker.quit()

        self._worker = TranslationWorker(
            text=self._source_text,
            source_lang="auto",
            target_lang=self.current_target_code(),
            parent=self,
        )
        self._worker.finishedTranslation.connect(self._on_translation_ready)
        self._worker.start()

    def _on_translation_ready(self, res: TranslationResult) -> None:
        if res.error:
            self.output_edit.setPlainText(res.error)
            self.status_lbl.setText("Error during translation")
            return
        self._translated_text = res.translated_text
        self._detected_source_lang = res.detected_lang or "auto"
        self.output_edit.setPlainText(res.translated_text)
        det_name = self.lang_code_to_name.get(self._detected_source_lang, self._detected_source_lang).title()
        self.status_lbl.setText(f"Detected: {det_name} | Double-click any word")

    def _copy_translation(self) -> None:
        if not self._translated_text:
            return
        self.mark_internal_copy_cb()
        QApplication.clipboard().setText(self._translated_text, QClipboard.Mode.Clipboard)
        self.copy_btn.setText("Copied")
        QTimer.singleShot(1300, lambda: self.copy_btn.setText("Copy"))

    def _open_in_main(self) -> None:
        self.openInMainRequested.emit(self._source_text, self.current_target_code())
        if not self._pinned:
            self.hide()

    def _toggle_pin(self, checked: bool) -> None:
        self._pinned = checked
        self.pin_btn.setStyleSheet(
            "background-color:#4f46e5; color:white; border-radius:6px;" if checked else ""
        )

    def _position_near_cursor(self) -> None:
        if self.isVisible() and self._pinned:
            return
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is None:
            self.move(pos + QPoint(16, 16))
            return
        avail = screen.availableGeometry()
        if pos.x() <= 1 and pos.y() <= 1:
            x = avail.center().x() - self.width() // 2
            y = avail.top() + 80
        else:
            x = min(max(avail.left() + 12, pos.x() - self.width() // 3), avail.right() - self.width() - 12)
            y = pos.y() + 22
            if y + self.height() > avail.bottom() - 12:
                y = max(avail.top() + 12, pos.y() - self.height() - 18)
        self.move(x, y)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None


# =============================================================================
# 10. PREMIUM DARK MODE STYLESHEET (QSS)
# =============================================================================
MODERN_DARK_QSS = """
QMainWindow, QWidget#CentralSurface {
    background-color: #0d0f17;
    color: #f1f5f9;
    font-family: 'Cantarell', 'Inter', 'Noto Sans', 'Segoe UI', sans-serif;
    font-size: 14px;
}

QFrame#HeaderBar, QFrame#LanguageBar {
    background-color: #141824;
    border: 1px solid #22283a;
    border-radius: 14px;
}

QFrame#EditorCard, QFrame#DictionaryCard {
    background-color: #141824;
    border: 1px solid #23293d;
    border-radius: 14px;
}

QFrame#EditorCard:hover {
    border: 1px solid #333c57;
}

QFrame#FloatingMiniContainer, QFrame#PopupCard {
    background-color: #131724;
    border: 1px solid #3b4261;
    border-radius: 16px;
}

QTextEdit#SourceEdit, QTextEdit#TargetEdit {
    background-color: #191e2e;
    color: #f8fafc;
    border: 1px solid #262d42;
    border-radius: 10px;
    padding: 12px;
    font-size: 15px;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
}

QTextEdit#SourceEdit:focus, QTextEdit#TargetEdit:focus {
    border: 1px solid #6366f1;
    background-color: #1b2032;
}

QTextEdit#DictionaryView, QTextEdit#DictPopupView {
    background-color: #181c2b;
    color: #e2e8f0;
    border: 1px solid #242b3d;
    border-radius: 10px;
    padding: 8px;
    font-size: 13px;
}

QTextEdit#MiniOutputEdit {
    background-color: #191e2e;
    color: #f8fafc;
    border: 1px solid #283048;
    border-radius: 10px;
    padding: 10px;
    font-size: 14px;
}

QComboBox {
    background-color: #1c2234;
    color: #f1f5f9;
    border: 1px solid #2c3550;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 600;
    font-size: 13px;
    min-height: 22px;
}

QComboBox:hover {
    border: 1px solid #6366f1;
    background-color: #21283d;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
}

QComboBox QAbstractItemView {
    background-color: #181d2c;
    color: #f1f5f9;
    border: 1px solid #3b4261;
    border-radius: 8px;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
    padding: 4px;
}

QComboBox#MiniCombo {
    padding: 4px 10px;
    min-height: 18px;
    font-size: 12px;
}

QPushButton#PrimaryBtn {
    background-color: #6366f1;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 9px 18px;
    font-weight: 700;
    font-size: 13px;
}

QPushButton#PrimaryBtn:hover {
    background-color: #4f46e5;
}

QPushButton#PrimaryBtn:pressed {
    background-color: #4338ca;
}

QPushButton#SecondaryBtn, QPushButton#MiniActionBtn {
    background-color: #1e2436;
    color: #cbd5e1;
    border: 1px solid #2b334d;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton#SecondaryBtn:hover, QPushButton#MiniActionBtn:hover {
    background-color: #283048;
    color: #ffffff;
    border: 1px solid #4f46e5;
}

QPushButton#WarnBtn {
    background-color: #3b2314;
    color: #fbbf24;
    border: 1px solid #f59e0b;
    border-radius: 8px;
    padding: 5px 10px;
    font-weight: 700;
    font-size: 11px;
}

QPushButton#WarnBtn:hover {
    background-color: #4d2d18;
    color: #fde68a;
}

QPushButton#OkBadgeBtn {
    background-color: #132a26;
    color: #34d399;
    border: 1px solid #10b981;
    border-radius: 8px;
    padding: 5px 10px;
    font-weight: 700;
    font-size: 11px;
}

QPushButton#MiniPrimaryBtn {
    background-color: #6366f1;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 700;
    font-size: 12px;
}

QPushButton#MiniPrimaryBtn:hover {
    background-color: #4f46e5;
}

QPushButton#SwapBtn {
    background-color: #1f2538;
    color: #a5b4fc;
    border: 1px solid #303956;
    border-radius: 10px;
    padding: 7px 14px;
}

QPushButton#SwapBtn:hover {
    background-color: #4f46e5;
    color: #ffffff;
    border: 1px solid #6366f1;
}

QPushButton#IconCloseBtn {
    background-color: transparent;
    color: #94a3b8;
    border: 1px solid transparent;
    border-radius: 6px;
}

QPushButton#IconCloseBtn:hover {
    background-color: #ef4444;
    color: #ffffff;
}

QCheckBox {
    color: #cbd5e1;
    font-size: 12px;
    font-weight: 600;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #191e2e;
}

QCheckBox::indicator:checked {
    background-color: #6366f1;
    border: 1px solid #818cf8;
}

QScrollBar:vertical {
    background: #141824;
    width: 8px;
    margin: 2px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #334155;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #6366f1;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""


# =============================================================================
# 11. MAIN APPLICATION WINDOW
# =============================================================================
class FedoraTranslatorWindow(QMainWindow):
    """Main Standalone Desktop Translation Studio for Fedora Linux."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Fedora Translate Studio - Google Translate & Dictionary")
        self.setWindowIcon(VectorIcons.globe("#818cf8", 24))
        self.resize(1220, 760)
        self.setMinimumSize(940, 580)

        self.lang_name_to_code: Dict[str, str] = dict(FALLBACK_GOOGLE_LANGUAGES)
        self.lang_code_to_name: Dict[str, str] = {v: k for k, v in self.lang_name_to_code.items()}
        self.lang_code_to_name["auto"] = "Auto Detect"

        self.last_detected_source_code: str = "en"
        self.current_dict_word: str = ""
        self.current_dict_lang: str = "en"

        self._translation_worker: Optional[TranslationWorker] = None
        self._dict_worker: Optional[DictionaryWorker] = None
        self._tts_worker: Optional[TTSWorker] = None
        self._lang_worker: Optional[LanguageLoaderWorker] = None

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(500)
        self._debounce_timer.timeout.connect(self.trigger_translation)

        self._build_ui()

        self.dict_popup = FloatingDictionaryPopup(self)
        self.dict_popup.pronounceRequested.connect(self.speak_text)

        self.hotkey_monitor = GlobalDoubleCopyMonitor(self)
        self.hotkey_monitor.doubleCopyTriggered.connect(self._on_global_double_copy)
        self.hotkey_monitor.statusChanged.connect(self._on_hotkey_status_changed)

        self.floating_mini = FloatingMiniTranslator(
            lang_name_to_code=self.lang_name_to_code,
            lang_code_to_name=self.lang_code_to_name,
            mark_internal_copy_cb=self.hotkey_monitor.mark_internal_copy,
        )
        self.floating_mini.openInMainRequested.connect(self._on_open_from_mini)
        self.floating_mini.speakRequested.connect(self.speak_text)
        self.floating_mini.wordLookupRequested.connect(self._on_word_double_clicked)

        self.hotkey_monitor.start()
        self._setup_tray_icon()
        self._start_language_fetch()

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("CentralSurface")
        self.setCentralWidget(central)

        main_vbox = QVBoxLayout(central)
        main_vbox.setContentsMargins(16, 14, 16, 14)
        main_vbox.setSpacing(10)

        # 1. Clean Two-Row Header Card
        header_frame = QFrame()
        header_frame.setObjectName("HeaderBar")
        header_vbox = QVBoxLayout(header_frame)
        header_vbox.setContentsMargins(16, 10, 16, 10)
        header_vbox.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(VectorIcons.globe("#818cf8", 22).pixmap(22, 22))
        top_row.addWidget(logo_lbl)

        title_lbl = QLabel("Fedora Translate Studio")
        title_lbl.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        title_lbl.setStyleSheet("font-size:17px; font-weight:800; color:#f8fafc;")
        top_row.addWidget(title_lbl)

        self.env_badge = QLabel(f"Fedora {REAL_SESSION_TYPE} | 133 Languages")
        self.env_badge.setStyleSheet(
            "background-color:#1e293b; color:#38bdf8; border:1px solid #334155; "
            "border-radius:8px; padding:4px 10px; font-size:11px; font-weight:700;"
        )
        top_row.addWidget(self.env_badge)

        self.key_hook_btn = QPushButton("Checking Key Hook...")
        self.key_hook_btn.setObjectName("OkBadgeBtn")
        self.key_hook_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.key_hook_btn.clicked.connect(self._enable_wayland_key_hook_dialog)
        top_row.addWidget(self.key_hook_btn)

        top_row.addStretch()

        test_popup_btn = QPushButton("Test Mini-Popup")
        test_popup_btn.setIcon(VectorIcons.bolt("#fbbf24", 14))
        test_popup_btn.setObjectName("SecondaryBtn")
        test_popup_btn.setToolTip("Open the floating Ctrl+C+C mini-window immediately")
        test_popup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_popup_btn.clicked.connect(self._test_mini_popup)
        top_row.addWidget(test_popup_btn)

        self.toggle_dict_btn = QPushButton("Dictionary Panel")
        self.toggle_dict_btn.setIcon(VectorIcons.book("#c084fc", 15))
        self.toggle_dict_btn.setObjectName("SecondaryBtn")
        self.toggle_dict_btn.setCheckable(True)
        self.toggle_dict_btn.setChecked(True)
        self.toggle_dict_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_dict_btn.toggled.connect(self._toggle_dictionary_panel)
        top_row.addWidget(self.toggle_dict_btn)

        header_vbox.addLayout(top_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)

        subtitle_lbl = QLabel(
            "Google Translate Engine  |  Double-click any word for Dictionary  |  Press Ctrl+C+C anywhere for Floating Translator"
        )
        subtitle_lbl.setStyleSheet("font-size:12px; color:#94a3b8;")
        bottom_row.addWidget(subtitle_lbl)

        bottom_row.addStretch()

        self.hotkey_toggle = QCheckBox("Global Ctrl+C+C")
        self.hotkey_toggle.setChecked(True)
        self.hotkey_toggle.toggled.connect(self._on_toggle_hotkey)
        bottom_row.addWidget(self.hotkey_toggle)

        self.single_copy_toggle = QCheckBox("1-Copy Auto Popup")
        self.single_copy_toggle.setChecked(False)
        self.single_copy_toggle.setToolTip(
            "When checked, copying text once (single Ctrl+C) immediately pops up the floating translator."
        )
        self.single_copy_toggle.toggled.connect(self._on_toggle_single_copy)
        bottom_row.addWidget(self.single_copy_toggle)

        self.popup_dict_toggle = QCheckBox("Popup Card on Double-Click")
        self.popup_dict_toggle.setChecked(True)
        bottom_row.addWidget(self.popup_dict_toggle)

        header_vbox.addLayout(bottom_row)
        main_vbox.addWidget(header_frame)

        # 2. Language Selector Bar
        lang_frame = QFrame()
        lang_frame.setObjectName("LanguageBar")
        lang_layout = QHBoxLayout(lang_frame)
        lang_layout.setContentsMargins(16, 9, 16, 9)
        lang_layout.setSpacing(12)

        src_lbl = QLabel("From:")
        src_lbl.setStyleSheet("color:#94a3b8; font-weight:700; font-size:12px;")
        lang_layout.addWidget(src_lbl)

        self.source_combo = QComboBox()
        self.source_combo.setEditable(True)
        self.source_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.source_combo.setMinimumWidth(220)
        lang_layout.addWidget(self.source_combo, stretch=1)

        self.swap_btn = QPushButton()
        self.swap_btn.setIcon(VectorIcons.swap("#a5b4fc", 18))
        self.swap_btn.setIconSize(QSize(18, 18))
        self.swap_btn.setObjectName("SwapBtn")
        self.swap_btn.setToolTip("Swap source and target languages (Ctrl+Shift+S)")
        self.swap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swap_btn.clicked.connect(self.swap_languages)
        lang_layout.addWidget(self.swap_btn)

        tgt_lbl = QLabel("To:")
        tgt_lbl.setStyleSheet("color:#94a3b8; font-weight:700; font-size:12px;")
        lang_layout.addWidget(tgt_lbl)

        self.target_combo = QComboBox()
        self.target_combo.setEditable(True)
        self.target_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.target_combo.setMinimumWidth(220)
        lang_layout.addWidget(self.target_combo, stretch=1)

        self.live_translate_cb = QCheckBox("Live Translate")
        self.live_translate_cb.setChecked(True)
        lang_layout.addWidget(self.live_translate_cb)

        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setIcon(VectorIcons.translate_arrow("#ffffff", 15))
        self.translate_btn.setObjectName("PrimaryBtn")
        self.translate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.translate_btn.clicked.connect(self.trigger_translation)
        lang_layout.addWidget(self.translate_btn)

        main_vbox.addWidget(lang_frame)

        self._populate_language_combos(self.lang_name_to_code, default_src="en", default_tgt="ar")
        self.source_combo.currentIndexChanged.connect(self.trigger_translation)
        self.target_combo.currentIndexChanged.connect(self.trigger_translation)

        # 3. Main Content Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(10)

        # --- Left: Source Input Card ---
        src_card = QFrame()
        src_card.setObjectName("EditorCard")
        src_vbox = QVBoxLayout(src_card)
        src_vbox.setContentsMargins(14, 12, 14, 12)
        src_vbox.setSpacing(8)

        src_top = QHBoxLayout()
        self.src_header_lbl = QLabel("SOURCE TEXT")
        self.src_header_lbl.setStyleSheet("color:#818cf8; font-weight:700; font-size:12px; letter-spacing:0.6px;")
        src_top.addWidget(self.src_header_lbl)
        src_top.addStretch()

        self.detected_badge = QLabel("")
        self.detected_badge.setStyleSheet("color:#38bdf8; font-size:11px; font-weight:600;")
        src_top.addWidget(self.detected_badge)
        src_vbox.addLayout(src_top)

        self.source_edit = DictionaryTextEdit(is_source=True, parent=src_card)
        self.source_edit.setObjectName("SourceEdit")
        self.source_edit.setPlaceholderText(
            "Type or paste text to translate...\n\n"
            "Tip: Double-click any word here (or in the translation) to view its parts of speech, "
            "alternative meanings, and synonyms!"
        )
        self.source_edit.textChanged.connect(self._on_source_text_changed)
        self.source_edit.wordDoubleClicked.connect(self._on_word_double_clicked)
        src_vbox.addWidget(self.source_edit, stretch=1)

        src_bottom = QHBoxLayout()
        self.char_count_lbl = QLabel("0 chars")
        self.char_count_lbl.setStyleSheet("color:#64748b; font-size:12px;")
        src_bottom.addWidget(self.char_count_lbl)
        src_bottom.addStretch()

        self.src_listen_btn = QPushButton("Listen")
        self.src_listen_btn.setIcon(VectorIcons.speaker("#e2e8f0", 15))
        self.src_listen_btn.setObjectName("SecondaryBtn")
        self.src_listen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.src_listen_btn.clicked.connect(self._speak_source)
        src_bottom.addWidget(self.src_listen_btn)

        paste_btn = QPushButton("Paste")
        paste_btn.setIcon(VectorIcons.paste("#e2e8f0", 15))
        paste_btn.setObjectName("SecondaryBtn")
        paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        paste_btn.clicked.connect(self._paste_source)
        src_bottom.addWidget(paste_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setIcon(VectorIcons.clear("#e2e8f0", 15))
        clear_btn.setObjectName("SecondaryBtn")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_all)
        src_bottom.addWidget(clear_btn)

        src_vbox.addLayout(src_bottom)
        self.main_splitter.addWidget(src_card)

        # --- Middle: Target Output Card ---
        tgt_card = QFrame()
        tgt_card.setObjectName("EditorCard")
        tgt_vbox = QVBoxLayout(tgt_card)
        tgt_vbox.setContentsMargins(14, 12, 14, 12)
        tgt_vbox.setSpacing(8)

        tgt_top = QHBoxLayout()
        self.tgt_header_lbl = QLabel("TRANSLATION")
        self.tgt_header_lbl.setStyleSheet("color:#38bdf8; font-weight:700; font-size:12px; letter-spacing:0.6px;")
        tgt_top.addWidget(self.tgt_header_lbl)
        tgt_top.addStretch()

        self.phonetic_lbl = QLabel("")
        self.phonetic_lbl.setStyleSheet("color:#94a3b8; font-size:12px; font-style:italic;")
        tgt_top.addWidget(self.phonetic_lbl)
        tgt_vbox.addLayout(tgt_top)

        self.target_edit = DictionaryTextEdit(is_source=False, parent=tgt_card)
        self.target_edit.setObjectName("TargetEdit")
        self.target_edit.setReadOnly(True)
        self.target_edit.setPlaceholderText("Translation will appear here...\n\n(Double-click any translated word for reverse dictionary lookup)")
        self.target_edit.wordDoubleClicked.connect(self._on_word_double_clicked)
        tgt_vbox.addWidget(self.target_edit, stretch=1)

        tgt_bottom = QHBoxLayout()
        self.trans_status_lbl = QLabel("Ready")
        self.trans_status_lbl.setStyleSheet("color:#64748b; font-size:12px;")
        tgt_bottom.addWidget(self.trans_status_lbl)
        tgt_bottom.addStretch()

        self.tgt_listen_btn = QPushButton("Listen")
        self.tgt_listen_btn.setIcon(VectorIcons.speaker("#e2e8f0", 15))
        self.tgt_listen_btn.setObjectName("SecondaryBtn")
        self.tgt_listen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tgt_listen_btn.clicked.connect(self._speak_target)
        tgt_bottom.addWidget(self.tgt_listen_btn)

        self.stop_audio_btn = QPushButton("Stop")
        self.stop_audio_btn.setIcon(VectorIcons.stop("#f87171", 15))
        self.stop_audio_btn.setObjectName("SecondaryBtn")
        self.stop_audio_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_audio_btn.clicked.connect(self.stop_tts)
        self.stop_audio_btn.setVisible(False)
        tgt_bottom.addWidget(self.stop_audio_btn)

        self.copy_tgt_btn = QPushButton("Copy")
        self.copy_tgt_btn.setIcon(VectorIcons.copy("#e2e8f0", 15))
        self.copy_tgt_btn.setObjectName("SecondaryBtn")
        self.copy_tgt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_tgt_btn.clicked.connect(self._copy_target)
        tgt_bottom.addWidget(self.copy_tgt_btn)

        tgt_vbox.addLayout(tgt_bottom)
        self.main_splitter.addWidget(tgt_card)

        # --- Right: Dedicated Double-Click Dictionary Side-Panel ---
        self.dict_card = QFrame()
        self.dict_card.setObjectName("DictionaryCard")
        self.dict_card.setMinimumWidth(300)
        dict_vbox = QVBoxLayout(self.dict_card)
        dict_vbox.setContentsMargins(14, 12, 14, 12)
        dict_vbox.setSpacing(8)

        dict_header = QHBoxLayout()
        dict_icon = QLabel()
        dict_icon.setPixmap(VectorIcons.book("#c084fc", 16).pixmap(16, 16))
        dict_header.addWidget(dict_icon)

        dict_title = QLabel("WORD DICTIONARY")
        dict_title.setStyleSheet("color:#c084fc; font-weight:700; font-size:12px; letter-spacing:0.6px;")
        dict_header.addWidget(dict_title)
        dict_header.addStretch()

        self.dict_speak_btn = QPushButton("Pronounce")
        self.dict_speak_btn.setIcon(VectorIcons.speaker("#e2e8f0", 14))
        self.dict_speak_btn.setObjectName("SecondaryBtn")
        self.dict_speak_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dict_speak_btn.setEnabled(False)
        self.dict_speak_btn.clicked.connect(
            lambda: self.speak_text(self.current_dict_word, self.current_dict_lang)
        )
        dict_header.addWidget(self.dict_speak_btn)
        dict_vbox.addLayout(dict_header)

        search_row = QHBoxLayout()
        self.dict_search_input = QLineEdit()
        self.dict_search_input.setPlaceholderText("Double-click a word or type here...")
        self.dict_search_input.setStyleSheet(
            "background-color:#191e2e; color:#f8fafc; border:1px solid #2b334d; "
            "border-radius:8px; padding:6px 10px; font-size:13px;"
        )
        self.dict_search_input.returnPressed.connect(self._on_manual_dict_search)
        search_row.addWidget(self.dict_search_input)

        dict_go_btn = QPushButton("Lookup")
        dict_go_btn.setObjectName("SecondaryBtn")
        dict_go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dict_go_btn.clicked.connect(self._on_manual_dict_search)
        search_row.addWidget(dict_go_btn)
        dict_vbox.addLayout(search_row)

        self.dict_browser = QTextEdit()
        self.dict_browser.setObjectName("DictionaryView")
        self.dict_browser.setReadOnly(True)
        self.dict_browser.setHtml(
            """
            <div style='color:#94a3b8; padding:12px; line-height:1.6;'>
                <b style='color:#e2e8f0; font-size:14px;'>Interactive Word Inspector</b><br><br>
                <b>Double-click any word</b> inside the Source or Translation text boxes to instantly view:
                <ul>
                    <li>Primary single-word translation</li>
                    <li>Parts of speech (<i>noun, verb, adjective...</i>)</li>
                    <li>Alternative meanings &amp; reverse translations</li>
                    <li>Synonyms &amp; definitions</li>
                </ul>
            </div>
            """
        )
        dict_vbox.addWidget(self.dict_browser, stretch=1)

        self.main_splitter.addWidget(self.dict_card)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 4)
        self.main_splitter.setStretchFactor(2, 3)

        main_vbox.addWidget(self.main_splitter, stretch=1)

        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.trigger_translation)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self).activated.connect(self.swap_languages)

    def _setup_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(VectorIcons.globe("#818cf8", 22), self)
        self.tray_icon.setToolTip("Fedora Translate Studio (Ctrl+C+C Active)")

        menu = QMenu()
        show_act = QAction("Open Fedora Translate Studio", self)
        show_act.triggered.connect(self._restore_main_window)
        menu.addAction(show_act)

        test_mini_act = QAction("Show Floating Mini-Translator", self)
        test_mini_act.triggered.connect(self._test_mini_popup)
        menu.addAction(test_mini_act)

        menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_act)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _on_hotkey_status_changed(self, text: str, is_optimal: bool) -> None:
        self.key_hook_btn.setText(text)
        self.key_hook_btn.setObjectName("OkBadgeBtn" if is_optimal else "WarnBtn")
        self.key_hook_btn.style().unpolish(self.key_hook_btn)
        self.key_hook_btn.style().polish(self.key_hook_btn)

    def _enable_wayland_key_hook_dialog(self) -> None:
        if self.hotkey_monitor.has_evdev_access:
            QMessageBox.information(
                self,
                "Global Ctrl+C+C Active",
                "Linux hardware key monitoring (/dev/input) is active!\n\n"
                "Pressing Ctrl+C twice rapidly (within 500ms) in any Wayland or X11 app "
                "will open the floating mini-translator.",
            )
            return

        user = os.environ.get("USER") or "user"
        cmd = f"setfacl -m u:{user}:r /dev/input/event*"
        ans = QMessageBox.question(
            self,
            "Enable Native Wayland Global Key Hook",
            "On Fedora GNOME Wayland, native Wayland apps isolate global keystrokes unless "
            "read access to /dev/input/event* is granted.\n\n"
            "Would you like to grant permission right now (via Fedora PolicyKit prompt) "
            "so Ctrl+C+C works across ALL Wayland apps immediately?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes and shutil.which("pkexec"):
            try:
                subprocess.run(["pkexec", "sh", "-c", cmd], check=False, timeout=30)
                if self.hotkey_monitor.restart_evdev():
                    QMessageBox.information(
                        self,
                        "Success",
                        "Wayland Global Ctrl+C+C hardware hook is now active across all apps!",
                    )
                    return
            except Exception:
                pass
            QMessageBox.warning(
                self,
                "Manual Command",
                f"Run this command once in your Fedora terminal:\n\nsudo {cmd}",
            )

    def _test_mini_popup(self) -> None:
        clip = read_linux_clipboard()
        sample = clip if clip else (self.source_edit.toPlainText().strip() or "Hello from Fedora Linux!")
        self.floating_mini.popup_and_grab_clipboard(
            target_code=self.current_target_code(),
            explicit_text=sample,
        )

    def _start_language_fetch(self) -> None:
        self._lang_worker = LanguageLoaderWorker(self)
        self._lang_worker.languagesLoaded.connect(self._on_languages_loaded)
        self._lang_worker.start()

    def _on_languages_loaded(self, langs: Dict[str, str]) -> None:
        if not langs:
            return
        self.lang_name_to_code = dict(langs)
        self.lang_code_to_name = {v: k for k, v in self.lang_name_to_code.items()}
        self.lang_code_to_name["auto"] = "Auto Detect"

        self._populate_language_combos(
            self.lang_name_to_code,
            default_src=self.current_source_code(),
            default_tgt=self.current_target_code(),
        )
        self.floating_mini.lang_name_to_code = self.lang_name_to_code
        self.floating_mini.lang_code_to_name = self.lang_code_to_name
        self.floating_mini.populate_languages(self.lang_name_to_code, default_code=self.current_target_code())

        self.env_badge.setText(f"Fedora {REAL_SESSION_TYPE} | {len(self.lang_name_to_code)} Google Languages")

    def _populate_language_combos(
        self,
        langs: Dict[str, str],
        default_src: str = "en",
        default_tgt: str = "ar",
    ) -> None:
        prev_src = self.source_combo.currentData() or default_src
        prev_tgt = self.target_combo.currentData() or default_tgt

        self.source_combo.blockSignals(True)
        self.target_combo.blockSignals(True)
        self.source_combo.clear()
        self.target_combo.clear()

        self.source_combo.addItem("Auto Detect (auto)", "auto")

        src_index = 0
        tgt_index = 0
        sorted_items = sorted(langs.items(), key=lambda kv: kv[0].lower())

        for idx, (name, code) in enumerate(sorted_items):
            label = f"{name.title()} ({code})"
            self.source_combo.addItem(label, code)
            self.target_combo.addItem(label, code)
            if code.lower() == prev_src.lower():
                src_index = idx + 1
            if code.lower() == prev_tgt.lower():
                tgt_index = idx

        self.source_combo.setCurrentIndex(src_index)
        self.target_combo.setCurrentIndex(tgt_index)

        for combo in (self.source_combo, self.target_combo):
            completer = combo.completer()
            if completer is not None:
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)

        self.source_combo.blockSignals(False)
        self.target_combo.blockSignals(False)

    def current_source_code(self) -> str:
        return self.source_combo.currentData() or "auto"

    def current_target_code(self) -> str:
        return self.target_combo.currentData() or "ar"

    def _on_source_text_changed(self) -> None:
        text = self.source_edit.toPlainText()
        self.char_count_lbl.setText(f"{len(text)} chars")
        if not text.strip():
            self.target_edit.clear()
            self.phonetic_lbl.clear()
            self.detected_badge.clear()
            self.trans_status_lbl.setText("Ready")
            return
        if self.live_translate_cb.isChecked():
            self._debounce_timer.start()

    def trigger_translation(self) -> None:
        text = self.source_edit.toPlainText().strip()
        if not text:
            return

        if self._translation_worker and self._translation_worker.isRunning():
            self._translation_worker.quit()

        self.trans_status_lbl.setText("Translating via Google Translate...")
        self._translation_worker = TranslationWorker(
            text=text,
            source_lang=self.current_source_code(),
            target_lang=self.current_target_code(),
            parent=self,
        )
        self._translation_worker.finishedTranslation.connect(self._on_translation_complete)
        self._translation_worker.start()

    def _on_translation_complete(self, res: TranslationResult) -> None:
        if res.error:
            self.trans_status_lbl.setText(res.error)
            return

        self.target_edit.setPlainText(res.translated_text)
        self.phonetic_lbl.setText(f"/{res.phonetic}/" if res.phonetic else "")

        if res.detected_lang:
            self.last_detected_source_code = res.detected_lang
            det_name = self.lang_code_to_name.get(res.detected_lang, res.detected_lang).title()
            if self.current_source_code() == "auto":
                self.detected_badge.setText(f"Detected: {det_name} ({res.detected_lang})")
            else:
                self.detected_badge.clear()

        tgt_name = self.lang_code_to_name.get(res.target_lang, res.target_lang).title()
        self.trans_status_lbl.setText(f"Translated to {tgt_name}")

    def swap_languages(self) -> None:
        src_code = self.current_source_code()
        tgt_code = self.current_target_code()
        if src_code == "auto":
            src_code = self.last_detected_source_code or "en"

        new_src_idx = self.source_combo.findData(tgt_code)
        new_tgt_idx = self.target_combo.findData(src_code)

        self.source_combo.blockSignals(True)
        self.target_combo.blockSignals(True)
        if new_src_idx >= 0:
            self.source_combo.setCurrentIndex(new_src_idx)
        if new_tgt_idx >= 0:
            self.target_combo.setCurrentIndex(new_tgt_idx)
        self.source_combo.blockSignals(False)
        self.target_combo.blockSignals(False)

        current_target_text = self.target_edit.toPlainText().strip()
        if current_target_text:
            self.source_edit.setPlainText(current_target_text)
            self.trigger_translation()

    def _on_word_double_clicked(self, word: str, is_source_area: bool, global_pos: QPoint) -> None:
        word = word.strip()
        if not word:
            return

        if is_source_area:
            src_lang = self.current_source_code()
            tgt_lang = self.current_target_code()
        else:
            src_lang = self.current_target_code()
            tgt_lang = (
                self.last_detected_source_code
                if self.current_source_code() == "auto"
                else self.current_source_code()
            )
            if src_lang == tgt_lang:
                tgt_lang = "en" if src_lang != "en" else "ar"

        self.dict_search_input.setText(word)
        self._run_dictionary_lookup(word, src_lang, tgt_lang, global_pos)

    def _on_manual_dict_search(self) -> None:
        word = self.dict_search_input.text().strip()
        if not word:
            return
        self._run_dictionary_lookup(
            word,
            self.current_source_code(),
            self.current_target_code(),
            global_pos=None,
        )

    def _run_dictionary_lookup(
        self,
        word: str,
        src_lang: str,
        tgt_lang: str,
        global_pos: Optional[QPoint] = None,
    ) -> None:
        if not self.dict_card.isVisible():
            self.dict_card.setVisible(True)
            self.toggle_dict_btn.setChecked(True)

        self.current_dict_word = word
        self.current_dict_lang = src_lang if src_lang != "auto" else self.last_detected_source_code
        self.dict_speak_btn.setEnabled(True)

        self.dict_browser.setHtml(
            f"<div style='color:#94a3b8; padding:12px;'>Looking up <b>{html.escape(word)}</b> in Google Translate Dictionary&hellip;</div>"
        )

        if global_pos is not None and (self.popup_dict_toggle.isChecked() or self.floating_mini.isVisible()):
            self.dict_popup.show_loading(word, global_pos)

        if self._dict_worker and self._dict_worker.isRunning():
            self._dict_worker.quit()

        self._dict_worker = DictionaryWorker(word=word, source_lang=src_lang, target_lang=tgt_lang, parent=self)
        self._dict_worker.finishedLookup.connect(self._on_dictionary_ready)
        self._dict_worker.start()

    def _on_dictionary_ready(self, res: DictionaryResult) -> None:
        self.current_dict_lang = res.detected_lang or res.source_lang or "en"
        rendered_html = format_dictionary_html(res, self.lang_code_to_name)
        self.dict_browser.setHtml(rendered_html)
        if self.dict_popup.isVisible():
            self.dict_popup.show_result(res, self.lang_code_to_name)

    def _toggle_dictionary_panel(self, visible: bool) -> None:
        self.dict_card.setVisible(visible)

    def _speak_source(self) -> None:
        text = self.source_edit.toPlainText().strip()
        lang = self.current_source_code()
        if lang == "auto":
            lang = self.last_detected_source_code or "auto"
        self.speak_text(text, lang)

    def _speak_target(self) -> None:
        text = self.target_edit.toPlainText().strip()
        lang = self.current_target_code()
        self.speak_text(text, lang)

    def speak_text(self, text: str, lang_code: str) -> None:
        if not text.strip():
            return
        self.stop_tts()

        self._tts_worker = TTSWorker(text=text, lang_code=lang_code, parent=self)
        self._tts_worker.playbackStarted.connect(self._on_tts_started)
        self._tts_worker.playbackFinished.connect(self._on_tts_finished)
        self._tts_worker.playbackError.connect(self._on_tts_error)
        self._tts_worker.start()

    def stop_tts(self) -> None:
        if self._tts_worker and self._tts_worker.isRunning():
            self._tts_worker.stop()
            self._tts_worker.wait(400)
        self.stop_audio_btn.setVisible(False)

    def _on_tts_started(self) -> None:
        self.stop_audio_btn.setVisible(True)
        self.trans_status_lbl.setText("Playing audio pronunciation...")

    def _on_tts_finished(self) -> None:
        self.stop_audio_btn.setVisible(False)
        self.trans_status_lbl.setText("Ready")

    def _on_tts_error(self, err_msg: str) -> None:
        self.stop_audio_btn.setVisible(False)
        self.trans_status_lbl.setText(err_msg)

    def _on_toggle_hotkey(self, checked: bool) -> None:
        self.hotkey_monitor.enabled = checked

    def _on_toggle_single_copy(self, checked: bool) -> None:
        self.hotkey_monitor.single_copy_mode = checked

    def _on_global_double_copy(self) -> None:
        self.floating_mini.popup_and_grab_clipboard(
            target_code=self.current_target_code(),
        )

    def _on_open_from_mini(self, source_text: str, target_code: str) -> None:
        self._restore_main_window()
        idx = self.target_combo.findData(target_code)
        if idx >= 0:
            self.target_combo.setCurrentIndex(idx)
        self.source_edit.setPlainText(source_text)
        self.trigger_translation()

    def _restore_main_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _paste_source(self) -> None:
        text = read_linux_clipboard()
        if text:
            self.source_edit.setPlainText(text)
            self.trigger_translation()

    def _clear_all(self) -> None:
        self.source_edit.clear()
        self.target_edit.clear()
        self.phonetic_lbl.clear()
        self.detected_badge.clear()
        self.trans_status_lbl.setText("Ready")

    def _copy_target(self) -> None:
        text = self.target_edit.toPlainText().strip()
        if not text:
            return
        self.hotkey_monitor.mark_internal_copy()
        QApplication.clipboard().setText(text, QClipboard.Mode.Clipboard)
        self.copy_tgt_btn.setText("Copied!")
        QTimer.singleShot(1400, lambda: self.copy_tgt_btn.setText("Copy"))

    def closeEvent(self, event) -> None:
        self.stop_tts()
        self.hotkey_monitor.stop()
        self.floating_mini.close()
        self.dict_popup.close()
        super().closeEvent(event)


# =============================================================================
# 12. APPLICATION ENTRY POINT
# =============================================================================
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Fedora Translate Studio")
    app.setOrganizationName("FedoraTranslateStudio")
    app.setStyleSheet(MODERN_DARK_QSS)
    app.setWindowIcon(QIcon(resource_path('logo.png')))
    window = FedoraTranslatorWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
