# -*- coding: utf-8 -*-
# Duden Bibliothek — PyGlossary Reader Plugin
#
# Reads a pre-decrypted Duden SQLite database and yields entries
# compatible with any PyGlossary writer (DSL, StarDict, MDict, etc.).
#
# The encrypted .nbof must be decrypted first using decrypt-duden.py.
# This reader operates only on standard, unencrypted SQLite databases.
#
# Schema reference: duden-reversed/database-schema-reference.md
from __future__ import annotations

import html
import logging
import re
import struct
import zlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	import sqlite3
	from collections.abc import Iterator

	from pyglossary.glossary_types import EntryType, ReaderGlossaryType

__all__ = ["Reader"]

log = logging.getLogger("pyglossary")

_re_sound_link = re.compile(
	r'<a\b[^>]*\bclass="soundlink"[^>]*>.*?</a>',
	re.DOTALL | re.IGNORECASE,
)
_re_meta_art_id = re.compile(
	r"<meta\b[^>]*\bart-id=[^>]*/?>",
	re.IGNORECASE,
)
_re_speaker_img = re.compile(
	r'<img\b[^>]*\bsrc="speaker\.png"[^>]*/?>',
	re.IGNORECASE,
)


def _decompress_blob(blob: bytes) -> str:
	"""Decompress a tabHtmlText.html BLOB.

	Format: 4-byte big-endian uncompressed size, then zlib-compressed data.
	"""
	if len(blob) < 5:
		return ""
	# first 4 bytes = uncompressed size (unused but present)
	_size = struct.unpack(">I", blob[:4])[0]
	return zlib.decompress(blob[4:]).decode("utf-8", errors="replace")


class Reader:
	useByteProgress = False

	# defaults for read-options (discovered via _-prefixed class attrs)
	_book_id: int = 300
	_include_resources: bool = True
	_strip_audio_links: bool = True
	_strip_art_id: bool = True

	def __init__(self, glos: ReaderGlossaryType) -> None:
		self._glos = glos
		self._clear()

	def _clear(self) -> None:
		self._filename = ""
		self._con: sqlite3.Connection | None = None
		self._cur: sqlite3.Cursor | None = None
		self._entry_count: int = 0

	def open(
		self,
		filename: str,
		book_id: int = 300,
		include_resources: bool = True,
		strip_audio_links: bool = True,
		strip_art_id: bool = True,
	) -> None:
		from sqlite3 import connect

		self._filename = filename
		self._book_id = book_id
		self._include_resources = include_resources
		self._strip_audio_links = strip_audio_links
		self._strip_art_id = strip_art_id

		self._con = connect(filename)
		self._cur = self._con.cursor()

		self._glos.setDefaultDefiFormat("h")

		# Read book metadata
		self._cur.execute(
			"SELECT desc, version, copyright, homepage, numarticles "
			"FROM tabBookDescription WHERE bookid = ?",
			(self._book_id,),
		)
		row = self._cur.fetchone()
		if row is not None:
			desc_raw, version, copyright_, homepage, numarticles = row
			# desc may contain HTML entities (e.g. &amp;)
			book_name = html.unescape(desc_raw) if desc_raw else ""
			if book_name:
				self._glos.setInfo("name", book_name)
			if version:
				self._glos.setInfo("version", str(version))
			if copyright_:
				self._glos.setInfo("copyright", html.unescape(copyright_))
			if homepage:
				self._glos.setInfo("website", homepage)
			if numarticles:
				self._entry_count = numarticles
		else:
			log.warning(
				f"No book metadata found for bookid={self._book_id}"
			)

		# Set language info (monolingual German dictionary)
		self._glos.sourceLangName = "German"
		self._glos.targetLangName = "German"

		# If entry count wasn't set from metadata, count directly
		if self._entry_count == 0:
			self._cur.execute(
				"SELECT count(*) FROM tabHtmlText "
				"WHERE lemma IS NOT NULL",
			)
			self._entry_count = self._cur.fetchone()[0]

	def __len__(self) -> int:
		return self._entry_count

	def _clean_html(self, raw_html: str) -> str:
		"""Apply optional HTML cleanup transforms."""
		result = raw_html
		if self._strip_art_id:
			result = _re_meta_art_id.sub("", result)
		if self._strip_audio_links:
			result = _re_sound_link.sub("", result)
			result = _re_speaker_img.sub("", result)
		return result

	def _iter_resources(self) -> Iterator[EntryType]:
		"""Yield DataEntry objects for embedded images and files."""
		if self._cur is None:
			return
		glos = self._glos

		# GUI bitmaps (PNG images referenced by HTML entries)
		self._cur.execute("SELECT filename, image FROM tabGUIBitmaps")
		for row in self._cur.fetchall():
			fname, data = row[0], row[1]
			if fname and data:
				yield glos.newDataEntry(fname, data)

		# External files (PDFs, docs)
		self._cur.execute("SELECT filename, content FROM tabExternFiles")
		for row in self._cur.fetchall():
			fname, data = row[0], row[1]
			if fname and data:
				yield glos.newDataEntry(fname, data)

	def __iter__(self) -> Iterator[EntryType]:
		if self._cur is None:
			raise ValueError("cur is None")
		glos = self._glos

		# Yield embedded resources first (images, PDFs)
		if self._include_resources:
			yield from self._iter_resources()

		# Main dictionary entries
		self._cur.execute(
			"SELECT lemma, html FROM tabHtmlText "
			"WHERE lemma IS NOT NULL "
			"ORDER BY lemma",
		)
		for row in self._cur.fetchall():
			lemma, blob = row[0], row[1]
			if blob is None:
				continue
			try:
				raw_html = _decompress_blob(blob)
			except (zlib.error, struct.error) as e:
				log.warning(
					f"Failed to decompress entry {lemma!r}: {e}"
				)
				continue

			term = html.unescape(lemma)
			definition = self._clean_html(raw_html)
			yield glos.newEntry(term, definition, defiFormat="h")

	def close(self) -> None:
		try:
			if self._cur:
				self._cur.close()
		except Exception:
			pass
		try:
			if self._con:
				self._con.close()
		except Exception:
			pass
		self._clear()
