"""Atlassian Document Format helpers.

Builders for the comments we push (clean rendering in Jira Cloud), and a
text extractor for the ADF payloads we pull (descriptions, custom fields).
"""


# ------------------------------------------------------------------ build


def doc(*content: dict) -> dict:
    return {"type": "doc", "version": 1, "content": list(content)}


def paragraph(text: str, bold: bool = False) -> dict:
    node: dict = {"type": "text", "text": text}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return {"type": "paragraph", "content": [node]}


def labelled(label: str, value: str) -> dict:
    """Paragraph like:  **Approver:** Jane Doe"""
    return {
        "type": "paragraph",
        "content": [
            {"type": "text", "text": f"{label}: ", "marks": [{"type": "strong"}]},
            {"type": "text", "text": value},
        ],
    }


def heading(text: str, level: int = 3) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def bullet_list(items: list[str]) -> dict:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": item}]}
                ],
            }
            for item in items
        ],
    }


def code_block(text: str, language: str | None = None) -> dict:
    node: dict = {"type": "codeBlock", "content": [{"type": "text", "text": text}]}
    if language:
        node["attrs"] = {"language": language}
    return node


def link_paragraph(text: str, url: str) -> dict:
    return {
        "type": "paragraph",
        "content": [
            {
                "type": "text",
                "text": text,
                "marks": [{"type": "link", "attrs": {"href": url}}],
            }
        ],
    }


# ---------------------------------------------------------------- extract


def adf_to_text(node) -> str:
    """Flatten an ADF document (or fragment) to readable plain text.
    Tolerates plain strings (Jira Server / already-text fields)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    if not isinstance(node, dict):
        return str(node)

    node_type = node.get("type")
    children = node.get("content", [])

    if node_type == "text":
        return node.get("text", "")
    if node_type == "hardBreak":
        return "\n"
    if node_type in ("paragraph", "heading"):
        return adf_to_text(children).rstrip() + "\n"
    if node_type in ("bulletList", "orderedList"):
        lines = []
        for item in children:  # listItems
            item_text = adf_to_text(item.get("content", [])).strip()
            lines.append(f"- {item_text}")
        return "\n".join(lines) + "\n"
    if node_type == "codeBlock":
        return adf_to_text(children) + "\n"
    # doc, blockquote, listItem content, tables, unknown containers
    return adf_to_text(children)
