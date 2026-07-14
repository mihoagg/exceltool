import re


def parse_dinh_dang(cell_value: str):
    cell_value = str(cell_value).strip()
    m = re.match(r'^(.+?)\s*\((.+)\)\s*$', cell_value)
    if m:
        return {"number": m.group(1).strip(), "requirements": m.group(2).strip()}
    return {"number": cell_value, "requirements": None}
