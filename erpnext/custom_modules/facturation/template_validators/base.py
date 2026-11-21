# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Shared machinery for the per-doctype template validators.

This module imports neither frappe nor the templates it checks: the same
code runs in the web worker and inside the sandboxed subprocess helpers,
and the doctype controllers / whitelisted API only call it.

ONE contract per editor mode (no 3-file contract):

- Python mode: ONE file. A metadata block of plain literals at the top
  (DOCUMENT_TYPE, TEMPLATE_NAME, PAGE, HEADER_FIELDS, LINE_COLUMNS,
  TOTAL_FIELDS, EXTRA_FIELDS, LANGUAGES) is read by AST — never executed
  for reading — and the entry point build(data, output_path) writes the
  xlsx and returns the path.
- HTML/CSS mode: TWO files. The HTML carries a single
  <script type="application/json" id="template-meta"> block with the same
  metadata keys plus Jinja placeholders (filters money, number, date_fr);
  the CSS lives in its own file. Rendered with a Jinja
  SandboxedEnvironment in the sandbox.

The declared metadata is reconciled with the validator's canonical
registry into a resolved extraction schema (the dynamic-metadata steps
1-4), then step 5 runs a differential sample test (datasets A: 1 line and
B: 25 lines) in the sandboxed subprocess."""

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

ALLOWED_FIELD_TYPES = ("text", "date", "number", "money", "percent", "bool", "list")
NUMERIC_TYPES = ("number", "money", "percent")
FIELD_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DATA_SECTIONS = ("header", "lines", "totals")
SECTIONS = DATA_SECTIONS + ("extra",)

PYTHON_METADATA_KEYS = (
	"DOCUMENT_TYPE",
	"TEMPLATE_NAME",
	"PAGE",
	"HEADER_FIELDS",
	"LINE_COLUMNS",
	"TOTAL_FIELDS",
	"EXTRA_FIELDS",
	"LANGUAGES",
)
ALLOWED_PYTHON_IMPORTS = frozenset({
	"PIL",
	"base64",
	"collections",
	"datetime",
	"decimal",
	"io",
	"itertools",
	"json",
	"math",
	"openpyxl",
	"re",
	"typing",
})
PYTHON_FORBIDDEN_CALLS = frozenset({"eval", "exec", "compile", "__import__", "open"})
SANDBOX_MEMORY_BYTES = 512 * 1024 * 1024
META_SCRIPT_ATTRS = {"type": "application/json", "id": "template-meta"}

# text present identically in datasets A and B that matches one of these
# patterns looks copied from a source document; plain labels and static
# branding do not match any of them
DATA_LIKE_PATTERNS = (
	re.compile(r"\d{4}-\d{2}-\d{2}"),                  # ISO dates
	re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),          # dates
	re.compile(r"\b\d+\.\d{3}\b"),                     # amounts (3 decimals, TND)
	re.compile(r"\b\d+\.\d{2}\b"),                     # amounts (2 decimals)
	re.compile(r"\b\d{6,}\b"),                         # long digit runs
	re.compile(r"\b[A-Z]{1,6}-\d{2,}[-/]\d{2,}(-\d+)?\b"),  # invoice-number-like codes
	re.compile(r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{3}\b"),  # tax-id-like strings
)


def hash_editor_contents(editor_mode: str, html_code: str, css_code: str, python_code: str) -> str:
	"""sha256 over the exact editor contents; the doctype controller and the
	validation API stamp/compare the same value."""
	payload = json.dumps([editor_mode or "", html_code or "", css_code or "", python_code or ""])
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def humanize_key(key: str) -> str:
	return str(key).replace("_", " ").strip().title()


def guess_type_from_key(key: str) -> str:
	"""Type guessed from the field-name suffix for inferred fields."""
	if str(key).startswith(("is_", "has_")):
		return "bool"
	if str(key).endswith(("_date", "_on", "_until", "_from")):
		return "date"
	if str(key).endswith(("_rate", "_percent")):
		return "percent"
	if str(key).endswith(("_amount", "_price", "_total", "_ht", "_ttc", "_timbre", "_base", "_fee")):
		return "money"
	if str(key).endswith(("_count", "_quantity", "_qty")):
		return "number"
	return "text"


def types_compatible(declared: str, used: str) -> bool:
	"""A declared type conflicts with the type inferred from usage only when
	they are really incompatible (numeric types are one family)."""
	if not declared or not used:
		return True
	if declared == used:
		return True
	return declared in NUMERIC_TYPES and used in NUMERIC_TYPES


def is_external_url(url: str) -> bool:
	"""CDN scripts, remote fonts/images and network references are external;
	data: URIs, inline SVG fragments and relative paths are not."""
	url = (url or "").strip().lower()
	if not url:
		return False
	return url.startswith(("http://", "https://", "//", "ftp:", "ws:", "data:application"))


# ---------------------------------------------------------------------------
# step 1: read the declared metadata (D)
# ---------------------------------------------------------------------------

def normalize_metadata(metadata: dict) -> tuple[dict, list]:
	"""Normalize the raw metadata block (same keys in both modes) into the
	declared-metadata shape; collects readable errors."""
	errors: list[str] = []
	declared: dict = {
		"document_type": "",
		"template_name": "",
		"page": {},
		"languages": [],
		"header": {},
		"lines": {},
		"totals": {},
		"extra": {},
	}
	declared["document_type"] = str(metadata.get("DOCUMENT_TYPE") or "").strip()
	declared["template_name"] = str(metadata.get("TEMPLATE_NAME") or "").strip()
	page = metadata.get("PAGE")
	if page is not None and not isinstance(page, dict):
		errors.append("metadata: PAGE must be an object {size, orientation}")
		page = {}
	declared["page"] = {str(k): str(v) for k, v in (page or {}).items()}
	languages = metadata.get("LANGUAGES")
	if languages is None:
		languages = []
	if not isinstance(languages, (list, tuple)):
		errors.append("metadata: LANGUAGES must be a list")
		languages = []
	declared["languages"] = [str(item) for item in languages]

	section_sources = (
		("header", "HEADER_FIELDS", metadata.get("HEADER_FIELDS")),
		("lines", "LINE_COLUMNS", metadata.get("LINE_COLUMNS")),
		("totals", "TOTAL_FIELDS", metadata.get("TOTAL_FIELDS")),
		("extra", "EXTRA_FIELDS", metadata.get("EXTRA_FIELDS")),
	)
	for section, key, raw in section_sources:
		if raw is None:
			continue
		items = raw
		if section == "lines":
			# LINE_COLUMNS is a list of {key, label, type}
			if not isinstance(items, (list, tuple)):
				errors.append(f"metadata: {key} must be a list of objects with key/label/type")
				continue
			converted = []
			for entry in items:
				if not isinstance(entry, dict) or "key" not in entry:
					errors.append(f"metadata: {key} entries need key/label/type")
					continue
				converted.append({str(entry.get("key")): entry})
			items = {}
			for entry in converted:
				items.update(entry)
		if not isinstance(items, dict):
			errors.append(f"metadata: {key} must map field keys to label/type objects")
			continue
		for field_key, spec in items.items():
			if not isinstance(spec, dict):
				errors.append(f"metadata: {key}.{field_key} must be an object with label/type")
				continue
			declared[section][str(field_key)] = {
				"label": str(spec.get("label") or "").strip(),
				"type": str(spec.get("type") or "").strip(),
			}
	return declared, errors


def read_python_metadata(source: str) -> tuple[dict, list]:
	"""AST-literal read of the module-level metadata block; the module is
	never executed for reading."""
	errors: list[str] = []
	try:
		tree = ast.parse(source or "")
	except SyntaxError as error:
		return {}, [f"python: syntax error: {error}"]
	metadata: dict = {}
	for node in tree.body:
		if (
			isinstance(node, ast.Assign)
			and len(node.targets) == 1
			and isinstance(node.targets[0], ast.Name)
			and node.targets[0].id in PYTHON_METADATA_KEYS
		):
			try:
				metadata[node.targets[0].id] = ast.literal_eval(node.value)
			except (ValueError, SyntaxError, TypeError):
				errors.append(f"python: {node.targets[0].id} must be plain literals (no function calls)")
	declared, normalize_errors = normalize_metadata(metadata)
	return declared, errors + normalize_errors


class _MetaBlockReader(HTMLParser):
	"""Collects the text of the single allowed metadata script block."""

	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.chunks: list[str] = []
		self._capture = False
		self._depth = 0

	def handle_starttag(self, tag, attrs) -> None:
		cleaned = {name.lower(): (value or "") for name, value in attrs}
		if (
			tag == "script"
			and cleaned.get("type") == META_SCRIPT_ATTRS["type"]
			and cleaned.get("id") == META_SCRIPT_ATTRS["id"]
		):
			self._capture = True
			self._depth = 1

	def handle_endtag(self, tag) -> None:
		if tag == "script" and self._capture:
			self._capture = False

	def handle_data(self, data) -> None:
		if self._capture:
			self.chunks.append(data)


def read_html_metadata(html: str) -> tuple[dict, list]:
	"""The metadata block is the single JSON script block in the HTML."""
	errors: list[str] = []
	reader = _MetaBlockReader()
	try:
		reader.feed(html or "")
		reader.close()
	except Exception as error:  # noqa: BLE001 — malformed HTML surfaces as a validation error
		return {}, [f"html: cannot parse the HTML ({error})"]
	if not reader.chunks:
		return {}, [
			'html: the metadata block <script type="application/json" id="template-meta"> is missing'
		]
	try:
		metadata = json.loads("".join(reader.chunks))
	except ValueError as error:
		return {}, [f"html: the metadata block is not valid JSON ({error})"]
	if not isinstance(metadata, dict):
		return {}, ["html: the metadata block must be a JSON object"]
	declared, normalize_errors = normalize_metadata(metadata)
	return declared, errors + normalize_errors


# ---------------------------------------------------------------------------
# static safety scans (fast-fail)
# ---------------------------------------------------------------------------

def scan_python(source: str) -> list[str]:
	errors: list[str] = []
	try:
		tree = ast.parse(source or "")
	except SyntaxError as error:
		return [f"python: syntax error: {error}"]
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			for alias in node.names:
				if alias.name.split(".")[0] not in ALLOWED_PYTHON_IMPORTS:
					errors.append(f"python: forbidden import '{alias.name}'")
		elif isinstance(node, ast.ImportFrom):
			root = (node.module or "").split(".")[0]
			if node.level:
				errors.append("python: relative imports are not allowed")
			elif root not in ALLOWED_PYTHON_IMPORTS:
				errors.append(f"python: forbidden import '{node.module}'")
		elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
			if node.func.id in PYTHON_FORBIDDEN_CALLS:
				if node.func.id == "open" and _references_output_path(node.args[:1]):
					continue
				errors.append(f"python: forbidden call {node.func.id}()")
	return errors


def _references_output_path(args) -> bool:
	"""open() is allowed only on the output path the contract hands over."""
	for arg in args:
		for node in ast.walk(arg):
			if isinstance(node, ast.Name) and node.id == "output_path":
				return True
	return False


class _HtmlScan(HTMLParser):
	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.errors: list[str] = []
		self._script_allowed = False
		self._button_text: list[str] = []
		self._button_depth = 0

	def handle_starttag(self, tag, attrs) -> None:
		cleaned = {name.lower(): (value or "") for name, value in attrs}
		if tag == "script":
			if (
				cleaned.get("type") == META_SCRIPT_ATTRS["type"]
				and cleaned.get("id") == META_SCRIPT_ATTRS["id"]
			):
				self._script_allowed = True
			else:
				self.errors.append("html: other <script> tags are forbidden (metadata block only)")
		if tag in ("iframe", "object", "embed", "style", "link", "base"):
			self.errors.append(f"html: <{tag}> is forbidden")
		for name, value in cleaned.items():
			if name.startswith("on"):
				self.errors.append(f"html: on* attribute '{name}' is forbidden")
			if name in ("src", "href", "srcset") and is_external_url(value):
				self.errors.append(f"html: external resource '{value}' is forbidden")
		if tag == "button":
			self._button_depth += 1
			self._button_text = []

	def handle_endtag(self, tag) -> None:
		if tag == "script":
			self._script_allowed = False
		if tag == "button" and self._button_depth:
			self._button_depth = 0
			text = " ".join(self._button_text).strip().lower()
			if any(word in text for word in ("print", "toolbar", "download")):
				self.errors.append(f"html: print/toolbar buttons are forbidden ('{text}')")

	def handle_data(self, data) -> None:
		if self._button_depth:
			self._button_text.append(data)


def scan_html(html: str) -> list[str]:
	scanner = _HtmlScan()
	try:
		scanner.feed(html or "")
		scanner.close()
	except Exception as error:  # noqa: BLE001 — malformed HTML surfaces as a validation error
		return [f"html: cannot parse the HTML ({error})"]
	return scanner.errors


def scan_css(css: str) -> list[str]:
	errors: list[str] = []
	if re.search(r"@import", css or "", re.IGNORECASE):
		errors.append("css: @import is forbidden")
	for match in re.finditer(r"url\(\s*['\"]?([^'\")]+)", css or "", re.IGNORECASE):
		if is_external_url(match.group(1).strip()):
			errors.append(f"css: external url '{match.group(1).strip()}' is forbidden")
	return errors


# ---------------------------------------------------------------------------
# step 2: infer the used keys (U), independently of the declarations
# ---------------------------------------------------------------------------

def _blank_usage() -> dict:
	return {section: {} for section in SECTIONS}


def _record(usage: dict, section: str, key: str, field_type: str | None = None, strong: bool = False) -> None:
	existing = usage.get(section, {}).get(key)
	if existing is None:
		usage[section][key] = {"type": field_type, "strong": strong}
	elif strong:
		usage[section][key] = {"type": field_type or existing.get("type"), "strong": True}


def infer_python(source: str) -> dict:
	"""AST walk over the generator: data["header"]["x"], data.get("header"),
	chained accesses, `for line in data["lines"]` with line["x"] and
	line.get("x"). Arithmetic marks the operands as strong numeric usage."""
	usage = _blank_usage()
	try:
		tree = ast.parse(source or "")
	except SyntaxError:
		return usage
	loop_vars: dict[str, tuple] = {}

	def resolve(node, depth: int = 0):
		"""Section path a node resolves to: () for `data` itself, ("header",)
		for data["header"], ("totals", "tva_by_rate") inside a loop."""
		if depth > 12:
			return None
		if isinstance(node, ast.Name):
			if node.id == "data":
				return ()
			if node.id in loop_vars:
				return loop_vars[node.id]
			return None
		if isinstance(node, ast.Subscript):
			slice_value = node.slice
			if isinstance(slice_value, ast.Constant) and isinstance(slice_value.value, str):
				base = resolve(node.value, depth + 1)
				if base is None:
					return None
				if len(base) == 0:
					if slice_value.value in SECTIONS:
						return (slice_value.value,)
					return None
				if len(base) == 1:
					return base + (slice_value.value,)
			return None
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
			if node.func.attr in ("get", "setdefault"):
				base = resolve(node.func.value, depth + 1)
				if base is None or len(base) > 1:
					return None
				first = node.args[0] if node.args else None
				if isinstance(first, ast.Constant) and isinstance(first.value, str):
					if len(base) == 0:
						if first.value in SECTIONS:
							return (first.value,)
						return None
					return base + (first.value,)
		return None

	for node in ast.walk(tree):
		if isinstance(node, (ast.For, ast.AsyncFor)):
			target = node.target
			bound = resolve(node.iter)
			if bound and isinstance(target, ast.Name):
				if len(bound) == 1 and bound[0] == "lines":
					loop_vars[target.id] = ("lines",)
				elif len(bound) == 2:
					loop_vars[target.id] = bound
			continue
		if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)):
			for operand in (node.left, node.right):
				base = resolve(operand)
				if base and len(base) == 2:
					# arithmetic on a scalar field: strong numeric usage
					_record(usage, base[0], base[1], "number", strong=True)
			continue
		if isinstance(node, ast.Subscript):
			slice_value = node.slice
			if isinstance(slice_value, ast.Constant) and isinstance(slice_value.value, str):
				base = resolve(node.value)
				if base and len(base) == 1:
					_record(usage, base[0], slice_value.value)
			continue
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
			if node.func.attr in ("get", "setdefault"):
				base = resolve(node.func.value)
				if base and len(base) == 1 and node.args:
					first = node.args[0]
					if isinstance(first, ast.Constant) and isinstance(first.value, str):
						_record(usage, base[0], first.value)
	return usage


JINJA_FILTER_TYPES = {
	"money": "money",
	"date_fr": "date",
	"number": "number",
	"int": "number",
	"float": "number",
}


def infer_html(html: str) -> dict:
	"""Jinja parse-tree walk: attribute paths, loop variables and the filters
	applied at the leaves (so types can be guessed from the filter used)."""
	usage = _blank_usage()
	try:
		from jinja2 import Environment, nodes

		tree = Environment().parse(html or "")
	except Exception:  # noqa: BLE001 — a template that does not parse fails the static stage
		return usage
	loop_vars: dict[str, tuple] = {}

	def path_of(node):
		"""(root_name, [keys], filter_name or None) for a dotted chain."""
		parts: list[str] = []
		filter_name = None
		current = node
		while True:
			if isinstance(current, nodes.Filter):
				filter_name = current.name
				current = current.node
			elif isinstance(current, nodes.Getattr):
				parts.insert(0, current.attr)
				current = current.node
			elif isinstance(current, nodes.Getitem):
				arg = current.arg
				if isinstance(arg, nodes.Const) and isinstance(arg.value, str):
					parts.insert(0, arg.value)
					current = current.node
				else:
					return None
			elif isinstance(current, nodes.Name):
				return (current.name, parts, filter_name)
			else:
				return None

	for node in (tree,):
		stack = [node]
		while stack:
			current = stack.pop()
			for child in current.iter_child_nodes():
				stack.append(child)
			if isinstance(current, nodes.For):
				target = current.target
				resolved = path_of(current.iter)
				if resolved and isinstance(target, nodes.Name):
					root, parts, _filt = resolved
					if root == "lines" and not parts:
						loop_vars[target.name] = ("lines",)
					elif root == "data" and len(parts) == 1:
						loop_vars[target.name] = (parts[0],)
					elif root in DATA_SECTIONS and len(parts) == 1:
						loop_vars[target.name] = (root, parts[0])
				continue
			resolved = path_of(current)
			if not resolved:
				continue
			root, parts, filter_name = resolved
			field_type = JINJA_FILTER_TYPES.get(filter_name or "")
			strong = bool(field_type)
			if root == "data" and parts and parts[0] in SECTIONS and len(parts) >= 2:
				_record(usage, parts[0], parts[1], field_type or None, strong)
			elif root in SECTIONS and parts:
				_record(usage, root, parts[0], field_type or None, strong)
			elif root in loop_vars and parts:
				bound = loop_vars[root]
				if len(bound) == 1:
					_record(usage, bound[0], parts[0], field_type or None, strong)
	return usage


# ---------------------------------------------------------------------------
# step 3 + 4: reconcile with the canonical registry -> resolved schema
# ---------------------------------------------------------------------------

def reconcile(canonical: dict, declared: dict, used: dict) -> tuple[dict, list, list]:
	"""D (declared) and U (used) are reconciled with C (canonical):

	- D and C        -> mapped canonical field
	- D not C        -> extension field (snake_case ASCII + label + allowed
	                    type) served from data.extra
	- U not D        -> added to the schema, marked inferred (warning)
	- D not U        -> dropped from the schema (warning)
	- required canonical field missing from D and U -> error
	- type conflicts -> error
	"""
	errors: list[str] = []
	warnings: list[str] = []
	schema: dict = {section: {} for section in SECTIONS}
	where_canonical = {
		key: section for section in DATA_SECTIONS for key in (canonical.get(section) or {})
	}
	# where each schema entry's declaration and usage were seen — a field
	# mapped across sections is compared against its SOURCE section in the
	# drop check
	declared_in: dict = {}
	used_in: dict = {}

	def canonical_entry(section: str, key: str) -> dict:
		return (canonical.get(section) or {})[key]

	def map_canonical(key: str, home: str, label: str) -> None:
		schema[home][key] = {
			"label": label or canonical_entry(home, key)["label"],
			"type": canonical_entry(home, key)["type"],
			"required": bool(canonical_entry(home, key).get("required")),
			"origin": "canonical",
		}

	# declared keys
	for section in DATA_SECTIONS:
		for key, spec in (declared.get(section) or {}).items():
			if not FIELD_KEY_PATTERN.match(str(key)):
				errors.append(f"{section}: '{key}' is not a snake_case ASCII field key")
				continue
			label = str(spec.get("label") or "").strip()
			field_type = str(spec.get("type") or "").strip()
			if field_type not in ALLOWED_FIELD_TYPES:
				errors.append(
					f"{section}.{key}: type '{field_type}' is not allowed (allowed: "
					+ ", ".join(ALLOWED_FIELD_TYPES) + ")"
				)
				continue
			if not label:
				errors.append(f"{section}.{key}: a label is required")
				continue
			home = section if key in (canonical.get(section) or {}) else where_canonical.get(key)
			if home:
				if home != section:
					warnings.append(f"{section}.{key}: canonical field of '{home}', mapped there")
				if not types_compatible(canonical_entry(home, key)["type"], field_type):
					warnings.append(
						f"{section}.{key}: declared as {field_type}, canonical type is "
						f"{canonical_entry(home, key)['type']}; using the canonical type"
					)
				map_canonical(key, home, label)
				declared_in[(home, key)] = section
			else:
				# extension field: served from data.extra
				schema["extra"][key] = {
					"label": label,
					"type": field_type,
					"required": False,
					"origin": "extension",
				}
				declared_in[("extra", key)] = section

	for key, spec in (declared.get("extra") or {}).items():
		# EXTRA_FIELDS entries are extensions by definition; a canonical
		# match is mapped home instead
		if not FIELD_KEY_PATTERN.match(str(key)):
			errors.append(f"extra: '{key}' is not a snake_case ASCII field key")
			continue
		label = str(spec.get("label") or "").strip()
		field_type = str(spec.get("type") or "").strip()
		if field_type not in ALLOWED_FIELD_TYPES:
			errors.append(
				f"extra.{key}: type '{field_type}' is not allowed (allowed: "
				+ ", ".join(ALLOWED_FIELD_TYPES) + ")"
			)
			continue
		if not label:
			errors.append(f"extra.{key}: a label is required")
			continue
		home = where_canonical.get(key)
		if home:
			warnings.append(f"extra.{key}: canonical field of '{home}', mapped there")
			map_canonical(key, home, label)
			declared_in[(home, key)] = "extra"
		else:
			schema["extra"][key] = {"label": label, "type": field_type, "required": False, "origin": "extension"}
			declared_in[("extra", key)] = "extra"

	# used keys
	for section in SECTIONS:
		for key, usage in (used.get(section) or {}).items():
			guessed = usage.get("type")
			strong = bool(usage.get("strong"))
			if (section, key) in declared_in:
				entry = schema[section][key]
				if strong and guessed and not types_compatible(entry.get("type"), guessed):
					errors.append(
						f"{section}.{key}: declared as {entry.get('type')} but used as {guessed}"
					)
				used_in[(section, key)] = section
				continue
			if key in (canonical.get(section) or {}):
				if strong and guessed and not types_compatible(
					canonical_entry(section, key)["type"], guessed
				):
					errors.append(
						f"{section}.{key}: used as {guessed} but the canonical type is "
						f"{canonical_entry(section, key)['type']}"
					)
					continue
				schema[section][key] = {
					"label": canonical_entry(section, key)["label"],
					"type": canonical_entry(section, key)["type"],
					"required": bool(canonical_entry(section, key).get("required")),
					"origin": "canonical",
					"inferred": True,
				}
				used_in[(section, key)] = section
				warnings.append(
					f"{section}.{key}: used but not declared; added from the canonical registry"
				)
			else:
				if not FIELD_KEY_PATTERN.match(str(key)):
					errors.append(f"{section}: '{key}' is not a snake_case ASCII field key")
					continue
				guess = guessed or guess_type_from_key(key)
				schema[section][key] = {
					"label": humanize_key(key),
					"type": guess,
					"required": False,
					"origin": "inferred",
				}
				used_in[(section, key)] = section
				warnings.append(f"{section}.{key}: used but not declared; inferred as {guess}")

	# required canonical coverage: missing from D and U is an error
	for section in DATA_SECTIONS:
		for key, spec in (canonical.get(section) or {}).items():
			if spec.get("required") and (section, key) not in declared_in and (section, key) not in used_in:
				errors.append(
					f"{section}.{key}: required canonical field is neither declared nor used"
				)

	# declared but never used: dropped from the schema, warning
	for (section, key), source_section in list(declared_in.items()):
		if (section, key) in used_in:
			continue
		if key in schema.get(section, {}):
			warnings.append(
				f"{section}.{key}: declared but never used; dropped from the schema"
			)
			del schema[section][key]

	# assemble the envelope
	out = {
		"document_type": declared.get("document_type") or "",
		"template_name": declared.get("template_name") or "",
		"page": declared.get("page") or {},
		"languages": declared.get("languages") or [],
	}
	out.update(schema)
	return out, errors, warnings


# ---------------------------------------------------------------------------
# sample datasets with distinctive tokens
# ---------------------------------------------------------------------------

def _stable_base(key: str) -> int:
	return 1000 + (int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:6], 16) % 8000)


def _sample_scalar(key: str, spec: dict, token: str) -> object:
	"""A distinctive value per field and per dataset (A/B), in a format the
	templates render verbatim with the contract filters."""
	field_type = spec.get("type")
	if field_type == "date":
		return "2026-01-15" if token == "A" else "2026-02-18"
	if field_type == "money":
		return round(_stable_base(key) + (0.111 if token == "A" else 0.222), 3)
	if field_type == "percent":
		return 19.0 if token == "A" else 10.0
	if field_type == "number":
		return 2 if token == "A" else 5
	if field_type == "bool":
		return token == "A"
	return f"{humanize_key(key)} {token}"


def _sample_line(section_schema: dict, token: str, index: int) -> dict:
	line = {}
	for key, spec in section_schema.items():
		if key == "designation" or spec.get("type") == "text":
			line[key] = f"{humanize_key(key)} {token}-L{index:03d}"
		elif key == "quantity" or spec.get("type") == "number":
			line[key] = (index % 5) + 1
		elif spec.get("type") == "money":
			line[key] = round(_stable_base(key) + index * 1.001 + (0.111 if token == "A" else 0.222), 3)
		elif spec.get("type") == "percent":
			line[key] = 19.0 if token == "A" else 10.0
		elif spec.get("type") == "date":
			line[key] = "2026-01-15" if token == "A" else "2026-02-18"
		elif spec.get("type") == "bool":
			line[key] = token == "A"
		else:
			line[key] = f"{humanize_key(key)} {token}-L{index:03d}"
	return line


def build_sample_dataset(schema: dict, token: str, line_count: int) -> dict:
	"""data = {"header": {...}, "lines": [{...}], "totals": {...}, "extra":
	{...}}; totals are computed from the lines so a computed total in the
	output can be compared against them."""
	data: dict = {"header": {}, "lines": [], "totals": {}, "extra": {}}
	for section in ("header",):
		for key, spec in (schema.get(section) or {}).items():
			data[section][key] = _sample_scalar(key, spec, token)
	for key, spec in (schema.get("extra") or {}).items():
		data["extra"][key] = _sample_scalar(key, spec, token)

	lines_schema = schema.get("lines") or {}
	for index in range(1, line_count + 1):
		line = _sample_line(lines_schema, token, index)
		if "quantity" in line and "unit_price" in line:
			quantity = float(line["quantity"])
			if "discount_percent" in line and line["discount_percent"]:
				line["amount_ht"] = round(
					quantity * float(line["unit_price"]) * (1 - float(line["discount_percent"]) / 100.0), 3
				)
			else:
				line["amount_ht"] = round(quantity * float(line["unit_price"]), 3)
		data["lines"].append(line)

	totals_schema = schema.get("totals") or {}
	amounts = [float(line.get("amount_ht") or 0.0) for line in data["lines"]]
	# totals are derived from the lines only when the line fields they are
	# computed from exist; otherwise every total gets its own distinctive
	# value (a template may render totals without line amounts at all)
	computable = "quantity" in lines_schema and "unit_price" in lines_schema
	totals: dict = {}
	if computable:
		if "total_ht" in totals_schema:
			totals["total_ht"] = round(sum(amounts), 3)
		if "discount_total" in totals_schema:
			totals["discount_total"] = round(sum(amounts) * (0.02 if token == "A" else 0.03), 3)
		if "net_ht" in totals_schema:
			totals["net_ht"] = round(totals.get("total_ht", sum(amounts)) - totals.get("discount_total", 0.0), 3)
		if "tva_by_rate" in totals_schema:
			rate = 19.0 if token == "A" else 13.0
			base = totals.get("net_ht", sum(amounts))
			totals["tva_by_rate"] = [
				{"rate": rate, "base": base, "amount": round(base * rate / 100.0, 3)}
			]
		if "tva_total" in totals_schema:
			totals["tva_total"] = round(
				sum(float(entry.get("amount") or 0.0) for entry in totals.get("tva_by_rate", [])), 3
			)
		if "timbre" in totals_schema:
			totals["timbre"] = 1.0 if token == "A" else 2.0
		if "total_ttc" in totals_schema:
			totals["total_ttc"] = round(
				totals.get("net_ht", sum(amounts))
				+ totals.get("tva_total", 0.0)
				+ totals.get("timbre", 0.0),
				3,
			)
	for key, spec in totals_schema.items():
		if key in totals:
			continue
		if spec.get("type") == "list":
			item_shape = spec.get("items") or {"value": {"type": "text"}}
			totals[key] = [
				{item_key: _sample_scalar(item_key, {"type": item_type}, token)}
				for item_key, item_type in item_shape.items()
			]
		else:
			totals[key] = _sample_scalar(key, spec, token)
	data["totals"] = totals
	return data


def _value_tokens(value: object, field_type: str) -> list[str]:
	"""Every string the template may legitimately render for this value."""
	if value is None or isinstance(value, (dict, list)):
		return []
	if field_type == "bool":
		return []
	tokens = []
	try:
		if field_type == "money":
			tokens.append(f"{float(value):.3f}")
		elif field_type == "number" and float(value) == int(float(value)):
			tokens.append(str(int(float(value))))
		elif field_type == "date":
			token = str(value)
			tokens.append(token)
			match = re.match(r"(\d{4})-(\d{2})-(\d{2})", token)
			if match:
				tokens.append(f"{match.group(3)}/{match.group(2)}/{match.group(1)}")
		else:
			tokens.append(str(value))
		if field_type in NUMERIC_TYPES and not isinstance(value, bool):
			tokens.append(str(value))
			tokens.append(f"{float(value):.3f}")
	except (TypeError, ValueError):
		tokens.append(str(value))
	return [token for token in tokens if token]


def _present(value: object, field_type: str, text: str) -> bool:
	return any(token in text for token in _value_tokens(value, field_type))


# ---------------------------------------------------------------------------
# output inspection
# ---------------------------------------------------------------------------

def extract_output_text(paths: list) -> str:
	"""All text an output carries: xlsx cell values (formulas included as
	text) or the rendered HTML stripped of its tags."""
	chunks: list[str] = []
	for path in paths:
		if str(path).endswith(".xlsx"):
			import openpyxl

			workbook = openpyxl.load_workbook(path, data_only=False)
			for worksheet in workbook.worksheets:
				for row in worksheet.iter_rows():
					for cell in row:
						if cell.value is not None:
							chunks.append(str(cell.value))
		elif str(path).endswith((".html", ".htm")):
			import html as html_module

			with open(path, "r", encoding="utf-8") as handle:
				source = handle.read()
			chunks.append(html_module.unescape(re.sub(r"<[^>]+>", " ", source)))
	return "\n".join(chunks)


def extract_output_grid(paths: list) -> list:
	"""(row, column, text) triples of the xlsx outputs, for the formula
	range checks."""
	grid: list[tuple] = []
	for path in paths:
		if not str(path).endswith(".xlsx"):
			continue
		import openpyxl

		workbook = openpyxl.load_workbook(path, data_only=False)
		for worksheet in workbook.worksheets:
			for row in worksheet.iter_rows():
				for cell in row:
					if cell.value is not None:
						grid.append((cell.row, cell.column, str(cell.value)))
	return grid


def _parse_sum_ranges(formula: str) -> list[tuple[int, int]]:
	"""Row spans of the =SUM(...) ranges inside a formula cell."""
	spans: list[tuple[int, int]] = []
	for match in re.finditer(r"SUM\(([^)]+)\)", formula.upper()):
		for part in match.group(1).split(","):
			bounds = re.match(r"^\s*[A-Z]+(\d+)\s*:\s*[A-Z]+(\d+)\s*$", part.strip())
			if bounds:
				spans.append((int(bounds.group(1)), int(bounds.group(2))))
	return spans


def check_total_formula_coverage(grid: list, line_rows: set) -> list[str]:
	"""A =SUM range over a column that carries line rows must cover every
	line row of dataset B (catches a fixed =SUM(G18:G20))."""
	if not line_rows:
		return []
	errors: list[str] = []
	line_columns = {column for row, column, _text in grid if row in line_rows}
	for row, column, text in grid:
		if not text.upper().startswith("=") or "SUM(" not in text.upper():
			continue
		for start, end in _parse_sum_ranges(text):
			if column in line_columns and (start > min(line_rows) or end < max(line_rows)):
				errors.append(
					f"the sum formula at row {row} covers rows {start}-{end} but dataset B has "
					f"lines on rows {min(line_rows)}-{max(line_rows)}"
				)
	return errors


def detect_hardcoded_data(text_a: str, text_b: str) -> list[str]:
	"""Text present identically in the outputs of datasets A and B that
	matches a data pattern (dates, invoice-number-like codes, amounts,
	long digit runs, tax ids)."""
	def tokenize(text: str) -> set:
		tokens = set()
		for line in text.splitlines():
			line = line.strip()
			if line:
				tokens.add(line)
			tokens.update(part for part in re.split(r"\s+", line) if part)
		return tokens

	common = tokenize(text_a) & tokenize(text_b)
	flagged = []
	for token in sorted(common):
		if any(pattern.search(token) for pattern in DATA_LIKE_PATTERNS):
			flagged.append(token)
	return flagged


# ---------------------------------------------------------------------------
# the sandboxed subprocess
# ---------------------------------------------------------------------------

def run_sandbox(task: str, payload: dict, timeout: int) -> dict:
	"""Run one task in the sandboxed subprocess (same approach and limits as
	print_designer's template_system._runner.py: separate process, RLIMIT_AS
	512 MB, no environment)."""
	runner = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sandbox_runner.py")
	try:
		proc = subprocess.run(
			[sys.executable, runner],
			input=json.dumps({"task": task, **payload}),
			capture_output=True,
			text=True,
			timeout=max(int(timeout or 30), 5),
			env={
				"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
				"HOME": tempfile.gettempdir(),
				"PYTHONDONTWRITEBYTECODE": "1",
			},
		)
	except subprocess.TimeoutExpired as error:
		raise TimeoutError(f"the template subprocess timed out after {timeout}s") from error
	result = None
	for line in reversed((proc.stdout or "").splitlines()):
		try:
			parsed = json.loads(line)
		except ValueError:
			continue
		if isinstance(parsed, dict) and parsed.get("ok"):
			result = parsed
			break
	if proc.returncode != 0 or not result:
		detail = ((proc.stderr or "") + " " + (proc.stdout or "")).strip()[-600:]
		raise RuntimeError(f"the template subprocess failed: {detail}")
	return result


# ---------------------------------------------------------------------------
# the validator base class
# ---------------------------------------------------------------------------

class BaseDocumentValidator:
	"""A validator owns one doctype's canonical registry and delegates the
	mode machinery (declared metadata, inference, scans, sandbox runs) to the
	shared code below; nothing doctype-specific may live there."""

	DOCUMENT_TYPE: str = ""
	# {"header": {key: {"label", "type", "required"}}, "lines": {...},
	#  "totals": {...}}; "list" fields may carry an "items" shape
	CANONICAL: dict = {}

	def _mode_engine(self, mode: str):
		if mode == "Python":
			return _PythonMode()
		if mode == "HTML/CSS":
			return _HtmlMode()
		raise ValueError(f"unknown editor mode: {mode}")

	def describe_contract(self) -> str:
		"""Markdown facts generated from this validator's own registry:
		canonical fields, allowed types, filters, forbidden constructs. It
		contains facts only, never instructions to an AI."""
		lines: list[str] = [
			f"# Contract reference — {self.DOCUMENT_TYPE}",
			"",
			"## Data shape",
			"",
			"`data = {\"header\": {...}, \"lines\": [{...}], \"totals\": {...}, \"extra\": {...}}`",
			"`extra` carries the extension fields this template declares or uses.",
			"",
			"## Canonical fields",
			"",
		]
		for section in DATA_SECTIONS:
			lines.append(f"### {section}")
			lines.append("")
			lines.append("| key | label | type | required |")
			lines.append("| --- | --- | --- | --- |")
			for key, spec in (self.CANONICAL.get(section) or {}).items():
				lines.append(
					f"| {key} | {spec.get('label')} | {spec.get('type')} "
					f"| {'yes' if spec.get('required') else 'no'} |"
				)
			lines.append("")
		lines += [
			"## Allowed field types",
			"",
			"text, date, number, money (3 decimals, TND), percent, bool, list",
			"",
			"## Jinja filters (HTML/CSS mode)",
			"",
			"money (3 decimals), number, date_fr (DD/MM/YYYY)",
			"",
			"## Metadata block (both modes)",
			"",
			"DOCUMENT_TYPE, TEMPLATE_NAME, PAGE {\"size\", \"orientation\"}, HEADER_FIELDS, "
			"LINE_COLUMNS, TOTAL_FIELDS, EXTRA_FIELDS, LANGUAGES",
			"",
			"## Forbidden (validation error)",
			"",
			"- any value copied from a source document (dates, invoice numbers, amounts, "
			"long digit runs, tax ids)",
			"- external resources (CDN scripts such as Tailwind, remote fonts/images, @import url)",
			"- other <script> tags, on*= attributes, iframes, print/toolbar buttons",
			"- network or file access outside the output path; images only as data: URIs or inline SVG",
		]
		return "\n".join(lines)

	def resolve_schema(self, mode: str, files: dict) -> tuple[dict, list, list]:
		"""Steps 1-4: static scan (fast-fail), declared metadata, inferred
		usage, reconciliation. Raises ValueError on scan/metadata errors."""
		engine = self._mode_engine(mode)
		scan_errors = engine.static_scan(files)
		if scan_errors:
			raise ValueError("\n".join(scan_errors))
		declared, declared_errors = engine.read_metadata(files)
		if declared_errors:
			raise ValueError("\n".join(declared_errors))
		used = engine.infer(files)
		if declared.get("document_type") and declared["document_type"] != self.DOCUMENT_TYPE:
			declared["document_type"] = self.DOCUMENT_TYPE
		schema, errors, warnings = reconcile(self.CANONICAL, declared, used)
		return schema, errors, warnings

	def validate(self, mode: str, files: dict, timeout: int | None = None) -> dict:
		"""Full validation: {status, log, schema}. Static safety scans run
		first and are fast-fail; the differential test runs in the sandboxed
		subprocess."""
		log: list[str] = []
		try:
			schema, errors, warnings = self.resolve_schema(mode, files)
		except ValueError as error:
			return {"status": "Failed", "log": [str(error)], "schema": {}}
		log.append("static safety scan: passed")
		if warnings:
			log.extend(f"warning: {warning}" for warning in warnings)
		if errors:
			log.extend(f"error: {error}" for error in errors)
			return {"status": "Failed", "log": log, "schema": schema}
		log.append(
			f"metadata reconciled: {sum(len(schema[s]) for s in SECTIONS)} fields in the resolved schema"
		)
		try:
			test_errors = self._run_differential(mode, files, schema, timeout, log)
		except TimeoutError as error:
			return {"status": "Failed", "log": log + [f"error: {error}"], "schema": schema}
		except (RuntimeError, ValueError) as error:
			return {"status": "Failed", "log": log + [f"error: {error}"], "schema": schema}
		if test_errors:
			log.extend(f"error: {error}" for error in test_errors)
			return {"status": "Failed", "log": log, "schema": schema}
		if warnings:
			return {"status": "Passed With Warnings", "log": log, "schema": schema}
		return {"status": "Passed", "log": log, "schema": schema}

	def generate(self, mode: str, files: dict, data: dict, out_dir: str, timeout: int | None = None) -> list:
		"""Run the generator once on data; returns the output paths."""
		os.makedirs(out_dir, exist_ok=True)
		engine = self._mode_engine(mode)
		return engine.generate(files, data, out_dir, timeout)

	def sample_datasets(self, schema: dict) -> list:
		"""Dataset A with 1 line and dataset B with 25 lines, with
		distinctive tokens; [{"tag": "A", "data": {...}}, ...]."""
		return [
			{"tag": "A", "data": build_sample_dataset(schema, "A", 1)},
			{"tag": "B", "data": build_sample_dataset(schema, "B", 25)},
		]

	def _run_differential(self, mode: str, files: dict, schema: dict, timeout: int | None, log: list) -> list:
		"""Step 5: the differential test. Returns error lines."""
		errors: list[str] = []
		datasets = self.sample_datasets(schema)
		runs: list[dict] = []
		with tempfile.TemporaryDirectory() as tmp:
			for index, entry in enumerate(datasets):
				tag = entry["tag"]
				out_dir = os.path.join(tmp, f"dataset_{tag}")
				try:
					paths = self.generate(mode, files, entry["data"], out_dir, timeout)
				except (RuntimeError, TimeoutError, OSError, ValueError) as error:
					return [f"differential test: dataset {tag} failed ({error})"]
				if not paths:
					return [f"differential test: dataset {tag} produced no output"]
				for path in paths:
					if not os.path.isfile(path) or os.path.getsize(path) == 0:
						return [f"differential test: dataset {tag} produced an empty output"]
				log.append(f"differential test: dataset {tag} generated {len(paths)} output(s)")
				text = extract_output_text(paths)
				runs.append({
					"tag": tag,
					"data": entry["data"],
					"paths": paths,
					"text": text,
					"grid": extract_output_grid(paths) if any(str(p).endswith(".xlsx") for p in paths) else [],
				})

			# b) every field of the schema shows up in the outputs of A and B
			for run in runs:
				tag = run["tag"]
				missing: list[str] = []
				for section in ("header", "totals", "extra"):
					for key, spec in (schema.get(section) or {}).items():
						value = run["data"].get(section, {}).get(key)
						if spec.get("type") == "list":
							continue  # list fields are covered by the line/item checks
						if not _present(value, spec.get("type"), run["text"]):
							missing.append(f"{section}.{key}")
				missing.extend(self._missing_line_fields(run, schema))
				if missing:
					errors.append(
						f"dataset {tag}: fields missing from the output: {', '.join(missing)}"
					)

			# c) all 25 lines of dataset B are present and sum ranges cover them
			run_b = runs[1]
			found_lines = sum(
				1 for index in range(1, 26)
				if f"-L{index:03d}" in run_b["text"] or f"L{index:03d}" in run_b["text"]
			)
			if found_lines < 25:
				errors.append(
					f"dataset B: only {found_lines} of the 25 lines show up in the output "
					"(a fixed row count?)"
				)
			for run in runs:
				if run["grid"]:
					line_rows = self._line_rows(run, schema)
					errors.extend(
						f"dataset {run['tag']}: {error}"
						for error in check_total_formula_coverage(run["grid"], line_rows)
					)

			# a computed total in the output matches the totals sent in the dataset
			ttc = (schema.get("totals") or {}).get("total_ttc")
			if ttc and run_b["data"]["totals"].get("total_ttc") is not None:
				has_value = _present(run_b["data"]["totals"]["total_ttc"], "money", run_b["text"])
				has_formula = bool(self._line_rows(run_b, schema)) and any(
					"SUM(" in text.upper()
					for _row, _column, text in run_b["grid"]
				)
				if not has_value and not has_formula:
					errors.append("dataset B: the total_ttc value does not show up in the output")

			# d) hard-coded data detector
			flagged = detect_hardcoded_data(runs[0]["text"], runs[1]["text"])
			for token in flagged:
				errors.append(f"the output text '{token}' looks copied from the source document")
		return errors

	def _line_rows(self, run: dict, schema: dict) -> set:
		rows: set = set()
		if not run["grid"]:
			return rows
		for index in range(1, 26):
			token = f"{run['tag']}-L{index:03d}"
			rows.update(row for row, _column, text in run["grid"] if token in text)
		return rows

	def _missing_line_fields(self, run: dict, schema: dict) -> list:
		"""Dataset A must render every line field; dataset B the first and
		the last line."""
		tag = run["tag"]
		lines_schema = schema.get("lines") or {}
		if not lines_schema:
			return []
		text = run["text"]
		missing: list[str] = []
		indices = range(1, len(run["data"]["lines"]) + 1) if tag == "A" else (1, len(run["data"]["lines"]))
		for index in indices:
			line = run["data"]["lines"][index - 1]
			for key, spec in lines_schema.items():
				value = line.get(key)
				if value is None or not _present(value, spec.get("type"), text):
					missing.append(f"lines.{key} (row {index})")
		return missing


# ---------------------------------------------------------------------------
# mode engines
# ---------------------------------------------------------------------------

class _PythonMode:
	def static_scan(self, files: dict) -> list:
		return scan_python(files.get("python") or "")

	def read_metadata(self, files: dict) -> tuple:
		return read_python_metadata(files.get("python") or "")

	def infer(self, files: dict) -> dict:
		return infer_python(files.get("python") or "")

	def generate(self, files: dict, data: dict, out_dir: str, timeout: int | None) -> list:
		module_path = os.path.join(out_dir, "template_module.py")
		with open(module_path, "w", encoding="utf-8") as handle:
			handle.write(files.get("python") or "")
		output_path = os.path.join(out_dir, "output.xlsx")
		run_sandbox(
			"python_build",
			{
				"template_dir": out_dir,
				"module_name": "template_module",
				"data": data,
				"output_path": output_path,
			},
			timeout,
		)
		return [output_path]


class _HtmlMode:
	def static_scan(self, files: dict) -> list:
		return scan_html(files.get("html") or "") + scan_css(files.get("css") or "")

	def read_metadata(self, files: dict) -> tuple:
		return read_html_metadata(files.get("html") or "")

	def infer(self, files: dict) -> dict:
		return infer_html(files.get("html") or "")

	def generate(self, files: dict, data: dict, out_dir: str, timeout: int | None) -> list:
		html_path = os.path.join(out_dir, "output.html")
		run_sandbox(
			"html_render",
			{
				"html": files.get("html") or "",
				"css": files.get("css") or "",
				"data": data,
				"output_path": html_path,
			},
			timeout,
		)
		return [html_path]
