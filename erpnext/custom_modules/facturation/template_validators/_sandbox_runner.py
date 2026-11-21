"""Subprocess runner for the per-doctype template validators.

Same approach and limits as print_designer's template_system/_runner.py:
separate process, RLIMIT_AS 512 MB, a scrubbed environment, a JSON payload
on stdin and a single JSON result line on stdout. Tasks:

- python_build: import the template module from template_dir and call
  build(data, output_path) — the Python-mode entry point.
- html_render: render the HTML (metadata block + Jinja placeholders) with a
  Jinja SandboundedEnvironment, inline the CSS, write the output.
"""

import json
import sys

try:
	import resource

	resource.setrlimit(
		resource.RLIMIT_AS,
		(512 * 1024 * 1024, 512 * 1024 * 1024),
	)
except Exception:  # noqa: BLE001 — the limit is best effort (not available everywhere)
	pass


def money(value) -> str:
	"""money: 3 decimals (TND context, no suffix)."""
	try:
		return f"{float(value):.3f}"
	except (TypeError, ValueError):
		return str(value)


def number(value) -> str:
	"""number: thousands-free, up to 3 decimals, trailing zeros trimmed."""
	try:
		floating = float(value)
	except (TypeError, ValueError):
		return str(value)
	if floating == int(floating):
		return str(int(floating))
	return f"{floating:.3f}".rstrip("0")


def date_fr(value) -> str:
	"""date_fr: ISO dates become DD/MM/YYYY; anything else passes through."""
	text = str(value or "")
	parts = text.split("-")
	if len(parts) == 3 and len(parts[0]) == 4:
		return f"{parts[2]}/{parts[1]}/{parts[0]}"
	return text


def python_build(payload: dict) -> None:
	template_dir = payload["template_dir"]
	if template_dir not in sys.path:
		sys.path.insert(0, template_dir)
	module = __import__(payload["module_name"])
	output_path = payload["output_path"]
	result = module.build(payload.get("data") or {}, output_path)
	print(json.dumps({"ok": True, "output": result or output_path}))


def html_render(payload: dict) -> None:
	from jinja2.sandbox import SandboxedEnvironment

	data = payload.get("data") or {}
	environment = SandboxedEnvironment()
	environment.filters["money"] = money
	environment.filters["number"] = number
	environment.filters["date_fr"] = date_fr
	rendered = environment.from_string(payload.get("html") or "").render(**data)
	css = payload.get("css") or ""
	if css:
		style_block = f"<style>{css}</style>"
		lower = rendered.lower()
		head_end = lower.find("</head>")
		if head_end >= 0:
			rendered = rendered[:head_end] + style_block + rendered[head_end:]
		else:
			rendered = style_block + rendered
	with open(payload["output_path"], "w", encoding="utf-8") as handle:
		handle.write(rendered)
	print(json.dumps({"ok": True, "output": payload["output_path"]}))


def main() -> None:
	payload = json.loads(sys.stdin.read() or "{}")
	task = payload.get("task")
	if task == "python_build":
		python_build(payload)
	elif task == "html_render":
		html_render(payload)
	else:
		raise ValueError(f"unknown sandbox task: {task}")


if __name__ == "__main__":
	main()
