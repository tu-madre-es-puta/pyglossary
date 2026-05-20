# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import TYPE_CHECKING

from pyglossary.option import BoolOption, IntOption, StrOption

from .reader import Reader

if TYPE_CHECKING:
	from pyglossary.option import Option

__all__ = [
	"Reader",
	"description",
	"enable",
	"extensionCreate",
	"extensions",
	"kind",
	"lname",
	"name",
	"optionsProp",
	"singleFile",
	"website",
	"wiki",
]

enable = True
lname = "duden_nbof"
name = "DudenNbof"
description = "Duden Bibliothek (SQLite3, German)"
extensions = ()
extensionCreate = ".db"
singleFile = True
kind = "binary"
wiki = ""
website = None
optionsProp: dict[str, Option] = {
	"book_id": IntOption(
		comment="Book ID to read (300 = Universalwörterbuch)",
	),
	"media_db": StrOption(
		comment="Path to decrypted dbmedia.bdb for audio pronunciations",
	),
	"include_resources": BoolOption(
		comment="Include images and external files as data entries",
	),
	"strip_audio_links": BoolOption(
		comment="Remove sound: links from HTML (auto-disabled when media_db is set)",
	),
	"strip_art_id": BoolOption(
		comment="Remove <meta art-id> tags from HTML definitions",
	),
}
