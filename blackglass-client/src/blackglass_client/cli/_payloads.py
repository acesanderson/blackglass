from __future__ import annotations


def patch_op_append(content: str) -> dict:
    return {"op": "append", "content": content}


def patch_op_prepend(content: str) -> dict:
    return {"op": "prepend", "content": content}


def patch_op_set_frontmatter(key: str, value: str) -> dict:
    return {"op": "set_frontmatter", "key": key, "value": value}


def patch_op_replace(old: str, new: str, replace_all: bool) -> dict:
    return {"op": "replace", "old": old, "new": new, "replace_all": replace_all}
