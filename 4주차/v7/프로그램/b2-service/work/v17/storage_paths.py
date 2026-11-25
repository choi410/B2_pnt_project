"""Resolve stored attachments in the current data folder after a package move."""
from pathlib import Path
import re


def rebase_record_paths(value, files):
    root = Path(files).resolve()

    def visit(item, key=''):
        if isinstance(item, dict):
            return {name: visit(child, name) for name, child in item.items()}
        if isinstance(item, list):
            return [visit(child, key) for child in item]
        if isinstance(item, str) and key in ('original_path', 'pdf', 'docx', 'txt'):
            match = re.search(r'(?:^|/)b2-service/data/[^/]+/files/(.+)$',
                              item.replace('\\', '/'), re.IGNORECASE)
            if match:
                relative = match[1]
                if any(part in ('', '.', '..') or ':' in part for part in relative.split('/')):
                    return item
                target = (root / relative).resolve()
                if target.is_relative_to(root):
                    return str(target)
        return item

    return visit(value)
