"""Organisation register: one canonical record for every organisation named in the data.

Names in disclosures are free text ("CT TNHH MTV ...", "Công ty TNHH Một Thành Viên ...", OCR
slips). Each spelling becomes an alias of one organisation, whose canonical name follows:

  <abbreviated legal form> <full own name>      e.g.  TNHH MTV Nông Nghiệp Xanh Thành Công
  - the structure word (Công ty, Tổng công ty, Viện, Quỹ, ...) is left out and kept in `kind`;
  - the legal form is abbreviated: CP, TNHH, TNHH MTV, TNHH 2TV, TMCP;
  - generic words abbreviated inside the own name are written out (TM -> Thương Mại, ...),
    brand acronyms (TTC, AgriS) are kept; words are capitalised, "và" stays lower case;
  - foreign organisations keep their registered name (legal form such as "Pte. Ltd" noted apart).

Organisations with different legal forms are different organisations, so the matching key is
(legal form, own name). People (key management, individual shareholders) and placeholder lines
are recorded as aliases without an organisation and never linked.

`build()` registers new names and links related_party_transactions, company_investments and
stock_holders to organisations; records marked "reviewed" are never changed by it. Reviews go
through a CSV: `export_review()` writes it, `apply_review()` applies the decisions.
"""

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

KINDS = [
    ("tong cong ty", "Tổng công ty"), ("cong ty", "Công ty"), ("cty", "Công ty"), ("ct", "Công ty"),
    ("doanh nghiep tu nhan", "Doanh nghiệp tư nhân"), ("hop tac xa", "Hợp tác xã"),
    ("ngan hang", "Ngân hàng"), ("vien", "Viện"), ("quy", "Quỹ"),
]
FORMS = [
    ("trach nhiem huu han hai thanh vien tro len", "TNHH 2TV"), ("tnhh hai thanh vien tro len", "TNHH 2TV"),
    ("trach nhiem huu han mot thanh vien", "TNHH MTV"), ("tnhh mot thanh vien", "TNHH MTV"),
    ("tnhh mtv", "TNHH MTV"), ("tnhh 2tv", "TNHH 2TV"), ("trach nhiem huu han", "TNHH"), ("tnhh", "TNHH"),
    ("thuong mai co phan", "TMCP"), ("tmcp", "TMCP"), ("co phan", "CP"), ("cp", "CP"),
]
FORM_WORDS = {
    "CP": "Cổ phần", "TNHH": "Trách nhiệm hữu hạn", "TNHH MTV": "Trách nhiệm hữu hạn Một thành viên",
    "TNHH 2TV": "Trách nhiệm hữu hạn Hai thành viên trở lên", "TMCP": "Thương mại Cổ phần",
}
EXPAND = {
    "tm": "Thương Mại", "dv": "Dịch Vụ", "sx": "Sản Xuất", "xnk": "Xuất Nhập Khẩu", "dt": "Đầu Tư",
    "xd": "Xây Dựng", "kcn": "Khu Công Nghiệp",
}
LOWER_WORDS = {"và"}
FOREIGN = re.compile(
    r"\b(pte\.?\s?ltd\.?|pty\.?\s?ltd\.?|co\.?,?\s?ltd\.?|inc\.?|limited|ltd\.?|llc|gmbh|mbh|"
    r"corp(?:oration)?\.?|plc|s\.?a\.?|b\.?v\.?|fund)(?=\W|$)", re.I)
PLACEHOLDERS = ("chua xac dinh", "cac thanh vien")
SOURCE_PRIORITY = {"manual": 0, "investment": 1, "related": 2, "holder": 3, "supply_chain": 4}


# Structure words put back in front of the canonical name when it is displayed in full
# ("Công ty" + "CP Đầu Tư Thành Thành Công"); foreign names are shown as registered.
DISPLAY_PREFIXES = ("Công ty", "Tổng công ty", "Doanh nghiệp tư nhân", "Hợp tác xã", "Ngân hàng", "Viện", "Quỹ")
_FOREIGN_SQL = "(^|[^[:alpha:]])(pte|pty|ltd|limited|inc|llc|gmbh|mbh|corp|corporation|plc|fund)([^[:alpha:]]|$)"


def display_name(canonical_name: str, kind: str | None) -> str:
    """Name for reading: the structure word followed by the canonical name, e.g.
    "Công ty TNHH MTV Thành Công Xanh", "Viện Nghiên Cứu Nông Nghiệp Thành Thành Công"."""
    if (not kind or kind not in DISPLAY_PREFIXES or FOREIGN.search(canonical_name)
            or fold(canonical_name).startswith(fold(kind) + " ")):
        return canonical_name
    return f"{kind} {canonical_name}"


def display_sql(alias: str) -> str:
    """SQL expression for display_name() of organisation row `alias` (NULL when there is none).
    Written without '%' so it can sit in queries that take parameters."""
    prefixes = ", ".join(f"'{p}'" for p in DISPLAY_PREFIXES)
    return (
        f"CASE WHEN {alias}.org_id IS NULL THEN NULL "
        f"WHEN {alias}.kind IN ({prefixes}) "
        f"AND {alias}.canonical_name NOT REGEXP '{_FOREIGN_SQL}' "
        f"AND LEFT(LOWER({alias}.canonical_name), CHAR_LENGTH({alias}.kind) + 1) <> CONCAT(LOWER({alias}.kind), ' ') "
        f"THEN CONCAT({alias}.kind, ' ', {alias}.canonical_name) "
        f"ELSE {alias}.canonical_name END"
    )


def fold(text: str) -> str:
    """Lower case without accents (đ -> d), for comparisons."""
    text = unicodedata.normalize("NFD", (text or "").lower()).replace("đ", "d")
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _words_key(text: str) -> str:
    return " ".join(w for w in re.sub(r"[^a-z0-9]+", " ", fold(text)).split() if w != "va")


@dataclass
class Parsed:
    raw: str
    kind: str | None
    legal_form: str | None
    name: str
    foreign: bool = False
    flags: list[str] = field(default_factory=list)

    @property
    def canonical(self) -> str:
        if self.foreign or not self.legal_form:
            return self.name
        return f"{self.legal_form} {self.name}"

    @property
    def full_name(self) -> str:
        if self.foreign:
            return self.name
        parts = [self.kind or "", FORM_WORDS.get(self.legal_form or "", ""), self.name]
        text = " ".join(p for p in parts if p)
        return text[:1].upper() + text[1:]

    @property
    def key(self) -> str:
        return f"{'foreign' if self.foreign else (self.legal_form or '-')}|{_words_key(self.name)}"


def _take(words: list[str], table: list[tuple[str, str]]) -> tuple[str | None, list[str]]:
    folded = [fold(w).strip(".,") for w in words]
    for phrase, value in table:
        parts = phrase.split()
        if folded[:len(parts)] == parts:
            return value, words[len(parts):]
    return None, words


def _word(word: str) -> str:
    plain = fold(word).strip(".,")
    if plain in EXPAND and word.strip(".,").isupper():
        return EXPAND[plain]
    if word.lower() in LOWER_WORDS:
        return word.lower()
    core = word.strip("()-,.")
    letters = [c for c in core if c.isalpha()]
    acronym = len(letters) >= 2 and all(c.isupper() for c in letters)
    brand = any(c.isupper() for c in core[1:]) and any(c.islower() for c in core)
    if acronym or brand:
        return word  # acronym or brand casing: TTC, AgriS
    return word[:1].upper() + word[1:].lower()


def parse(raw: str) -> Parsed:
    text = " ".join((raw or "").split())
    text = re.sub(r"^CTCP\b", "Công ty Cổ phần", text)
    match = FOREIGN.search(text)
    if match and not re.match(r"(?i)^(công ty|cty|ct)\s+(cổ phần|cp|tnhh|trách nhiệm)", text):
        name = re.sub(r"(?i)^(công ty|cty)\s+", "", text)
        fund = fold(match.group(1)) == "fund"
        return Parsed(raw, "Quỹ" if fund else "Công ty nước ngoài", None if fund else match.group(1), name,
                      foreign=True)
    words = text.split()
    kind, words = _take(words, KINDS)
    legal_form, words = _take(words, FORMS)
    name = " ".join(_word(w) for w in words)
    parsed = Parsed(raw, kind, legal_form, name)
    if not legal_form and kind not in ("Viện", "Quỹ", "Hợp tác xã", "Doanh nghiệp tư nhân"):
        parsed.flags.append("no legal form")
    if not kind:
        parsed.flags.append("no structure word")
    return parsed


def is_placeholder(name: str) -> bool:
    return fold(name).startswith(PLACEHOLDERS)


# --- database --------------------------------------------------------------------------------

def _rows(cursor: Any, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, tuple(params))
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def source_names(cursor: Any) -> list[tuple[str, str, bool]]:
    """(name, source, is_organisation) for every exact spelling in the source tables (binary
    comparison: the tables' collation would fold "Năng Lượng" and "Năng lượng" together)."""
    found: list[tuple[str, str, bool]] = []
    for row in _rows(cursor, "SELECT DISTINCT counterparty_name COLLATE utf8mb4_bin AS n, relationship AS r FROM related_party_transactions"):
        found.append((row["n"], "related", row["r"] != "key_management" and not is_placeholder(row["n"])))
    for row in _rows(cursor, "SELECT DISTINCT investee_name COLLATE utf8mb4_bin AS n FROM company_investments"):
        found.append((row["n"], "investment", not is_placeholder(row["n"])))
    for row in _rows(cursor, "SELECT DISTINCT holder_name COLLATE utf8mb4_bin AS n, holder_type AS t FROM stock_holders"):
        found.append((row["n"], "holder", row["t"] not in ("individual", "foreign_individual")))
    return found


def _listed_index(cursor: Any) -> dict[str, str]:
    index: dict[str, set[str]] = {}
    for row in _rows(cursor, "SELECT ticker, company_name FROM companies"):
        index.setdefault(parse(row["company_name"]).key, set()).add(row["ticker"])
    return {key: next(iter(t)) for key, t in index.items() if len(t) == 1}


def _org_keys(cursor: Any) -> dict[str, int]:
    """Matching key of every organisation, from its canonical name and all its aliases."""
    keys: dict[str, int] = {}
    for row in _rows(cursor, "SELECT org_id, canonical_name, kind, legal_form FROM organizations"):
        keys.setdefault(parse(_display_raw(row)).key, row["org_id"])
    for row in _rows(cursor, "SELECT alias, org_id FROM organization_aliases WHERE org_id IS NOT NULL"):
        keys.setdefault(parse(row["alias"]).key, row["org_id"])
    return keys


def _display_raw(row: dict[str, Any]) -> str:
    """Rebuild a parseable name from a stored organisation (canonical names omit the kind)."""
    if row["kind"] in ("Công ty nước ngoài", "Quỹ") and not row["legal_form"] in FORM_WORDS:
        return row["canonical_name"]
    return f"{row['kind'] or 'Công ty'} {row['canonical_name']}"


def build(connection: Any) -> dict[str, int]:
    """Register new names, refresh automatic organisations and link the source tables.

    Changes are left uncommitted. Returns counts of what changed.
    """
    cursor = connection.cursor()
    stats = {"organisations_created": 0, "aliases_added": 0, "not_organisations": 0, "linked": 0}
    known = {row["alias"] for row in _rows(cursor, "SELECT alias FROM organization_aliases")}
    keys = _org_keys(cursor)
    listed = _listed_index(cursor)

    new: dict[str, list[tuple[Parsed, str]]] = {}
    for name, source, is_org in source_names(cursor):
        if not name or name in known:
            continue
        known.add(name)
        if not is_org:
            cursor.execute("INSERT INTO organization_aliases (alias, org_id, source) VALUES (%s, NULL, %s)",
                           (name, source))
            stats["not_organisations"] += 1
            continue
        parsed = parse(name)
        if parsed.key in keys:
            cursor.execute("INSERT INTO organization_aliases (alias, org_id, source) VALUES (%s, %s, %s)",
                           (name, keys[parsed.key], source))
            stats["aliases_added"] += 1
        else:
            new.setdefault(parsed.key, []).append((parsed, source))

    for key, variants in new.items():
        # The fullest spelling becomes the canonical name ("Nghiên Cứu và Ứng Dụng" over "Nghiên Cứu, Ứng Dụng").
        best, _ = max(variants, key=lambda v: (len(v[0].name.split()), -SOURCE_PRIORITY.get(v[1], 9)))
        canonical = _unique_name(cursor, best.canonical)
        cursor.execute(
            """INSERT INTO organizations (canonical_name, full_name, kind, legal_form, ticker, country, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'auto')""",
            (canonical, best.full_name, best.kind, best.legal_form, listed.get(key),
             None if best.foreign else "Việt Nam"),
        )
        org_id = cursor.lastrowid
        keys[key] = org_id
        stats["organisations_created"] += 1
        for parsed, source in variants:
            cursor.execute("INSERT INTO organization_aliases (alias, org_id, source) VALUES (%s, %s, %s)",
                           (parsed.raw, org_id, source))
            stats["aliases_added"] += 1

    stats["renamed"] = _refresh_automatic(cursor, listed)
    stats["linked"] = link(cursor)
    cursor.close()
    return stats


def _refresh_automatic(cursor: Any, listed: dict[str, str]) -> int:
    """Recompute name, kind, legal form and ticker of organisations nobody has reviewed yet, from
    their aliases, so changes to the naming rules reach them. Reviewed records are left alone."""
    aliases: dict[int, list[tuple[str, str]]] = {}
    for row in _rows(cursor, """SELECT a.org_id, a.alias, a.source FROM organization_aliases AS a
                                JOIN organizations AS o USING (org_id) WHERE o.status = 'auto'"""):
        aliases.setdefault(row["org_id"], []).append((row["alias"], row["source"]))
    changed = 0
    for org in _rows(cursor, "SELECT * FROM organizations WHERE status = 'auto'"):
        variants = [(parse(alias), source) for alias, source in aliases.get(org["org_id"], [])
                    if source != "manual"]
        if not variants:
            continue
        best, _ = max(variants, key=lambda v: (len(v[0].name.split()), -SOURCE_PRIORITY.get(v[1], 9)))
        wanted = {"canonical_name": best.canonical, "full_name": best.full_name, "kind": best.kind,
                  "legal_form": best.legal_form, "ticker": org["ticker"] or listed.get(best.key)}
        if all(org[k] == v for k, v in wanted.items()):
            continue
        if wanted["canonical_name"] != org["canonical_name"]:
            wanted["canonical_name"] = _unique_name(cursor, wanted["canonical_name"])
        assignments = ", ".join(f"{k} = %s" for k in wanted)
        cursor.execute(f"UPDATE organizations SET {assignments} WHERE org_id = %s",
                       (*wanted.values(), org["org_id"]))
        changed += 1
    return changed


def _unique_name(cursor: Any, name: str) -> str:
    candidate, n = name, 2
    while _rows(cursor, "SELECT 1 AS x FROM organizations WHERE canonical_name = %s", (candidate,)):
        candidate = f"{name} ({n})"
        n += 1
    return candidate


def link(cursor: Any) -> int:
    """Point every source row at the organisation of its name (exact alias match)."""
    changed = 0
    for table, name_column, org_column in (
        ("related_party_transactions", "counterparty_name", "counterparty_org_id"),
        ("company_investments", "investee_name", "investee_org_id"),
        ("stock_holders", "holder_name", "holder_org_id"),
    ):
        cursor.execute(
            f"""UPDATE {table} AS t LEFT JOIN organization_aliases AS a
                  ON a.alias = t.{name_column} COLLATE utf8mb4_bin
                SET t.{org_column} = a.org_id
                WHERE NOT (t.{org_column} <=> a.org_id)""")
        changed += cursor.rowcount
    return changed


# --- review ----------------------------------------------------------------------------------

REVIEW_COLUMNS = ("org_id", "status", "canonical_name", "full_name", "kind", "legal_form", "ticker",
                  "tax_code", "country", "aliases", "flags", "action")


def review_flags(organisations: list[dict[str, Any]], aliases: dict[int, list[str]]) -> dict[int, list[str]]:
    flags: dict[int, list[str]] = {}
    own = {o["org_id"]: _words_key(parse(_display_raw(o)).name) for o in organisations}
    for org in organisations:
        found: list[str] = []
        parsed = parse(_display_raw(org))
        found.extend(f for f in parsed.flags if org["kind"] not in ("Viện", "Quỹ"))
        forms = {parse(a).legal_form for a in aliases.get(org["org_id"], []) if not parse(a).foreign}
        if len(forms - {None}) > 1:
            found.append("aliases with different legal forms")
        words = own[org["org_id"]].split()
        for other in organisations:
            if other["org_id"] == org["org_id"] or not words:
                continue
            if own[other["org_id"]] == own[org["org_id"]]:
                found.append(f"same name, other legal form: {other['canonical_name']}")
            elif (len(words) >= 2 and (org["legal_form"] or "") in ((other["legal_form"] or ""), "")
                  and _is_subsequence(words, own[other["org_id"]].split())):
                found.append(f"name contained in: {other['canonical_name']}")
        flags[org["org_id"]] = found
    return flags


def _is_subsequence(short: list[str], long: list[str]) -> bool:
    """True when every word of `short` appears in `long`, in order (and `long` has more words)."""
    if len(short) >= len(long):
        return False
    it = iter(long)
    return all(word in it for word in short)


def export_review(connection: Any, path: Path) -> int:
    cursor = connection.cursor()
    organisations = _rows(cursor, "SELECT * FROM organizations ORDER BY status, canonical_name")
    aliases: dict[int, list[str]] = {}
    for row in _rows(cursor, "SELECT org_id, alias FROM organization_aliases WHERE org_id IS NOT NULL ORDER BY alias"):
        aliases.setdefault(row["org_id"], []).append(row["alias"])
    cursor.close()
    flags = review_flags(organisations, aliases)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for org in organisations:
            writer.writerow({
                **{c: org.get(c) or "" for c in REVIEW_COLUMNS if c in org},
                "aliases": " | ".join(aliases.get(org["org_id"], [])),
                "flags": "; ".join(flags[org["org_id"]]),
                "action": "",
            })
    return len(organisations)


EDITABLE = ("canonical_name", "full_name", "kind", "legal_form", "ticker", "tax_code", "country")


def apply_review(connection: Any, path: Path) -> dict[str, int]:
    """Apply the `action` column of a review CSV:

      ok              keep the record (with any edits made in the row) and mark it reviewed
      merge:<target>  move this organisation's aliases to <target> (canonical name or org_id)
      not_org         the names are not an organisation (a person, a placeholder): unlink them
      (empty)         leave unchanged
    """
    stats = {"reviewed": 0, "merged": 0, "not_org": 0}
    cursor = connection.cursor()
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    for line, row in enumerate(rows, start=2):
        action = (row.get("action") or "").strip()
        if not action:
            continue
        org_id = int(row["org_id"])
        if not _rows(cursor, "SELECT org_id FROM organizations WHERE org_id = %s", (org_id,)):
            raise ValueError(f"{path.name}:{line}: organisation {org_id} does not exist")
        if action == "ok":
            values = {c: (row.get(c) or "").strip() or None for c in EDITABLE}
            if not values["canonical_name"]:
                raise ValueError(f"{path.name}:{line}: canonical_name is required")
            assignments = ", ".join(f"{c} = %s" for c in values)
            cursor.execute(f"UPDATE organizations SET {assignments}, status = 'reviewed' WHERE org_id = %s",
                           (*values.values(), org_id))
            stats["reviewed"] += 1
        elif action.startswith("merge:"):
            target = action.split(":", 1)[1].strip()
            found = _rows(cursor, "SELECT org_id FROM organizations WHERE org_id = %s OR canonical_name = %s",
                          (int(target) if target.isdigit() else -1, target))
            if not found or found[0]["org_id"] == org_id:
                raise ValueError(f"{path.name}:{line}: merge target {target!r} not found")
            _merge(cursor, org_id, found[0]["org_id"])
            stats["merged"] += 1
        elif action == "not_org":
            cursor.execute("UPDATE organization_aliases SET org_id = NULL WHERE org_id = %s", (org_id,))
            cursor.execute("DELETE FROM organizations WHERE org_id = %s", (org_id,))
            stats["not_org"] += 1
        else:
            raise ValueError(f"{path.name}:{line}: unknown action {action!r} (ok, merge:<target>, not_org)")
    link(cursor)
    cursor.close()
    return stats


def _merge(cursor: Any, source_id: int, target_id: int) -> None:
    """Fold one organisation into another: its canonical name becomes an alias of the target."""
    row = _rows(cursor, "SELECT canonical_name FROM organizations WHERE org_id = %s", (source_id,))[0]
    cursor.execute("UPDATE organization_aliases SET org_id = %s WHERE org_id = %s", (target_id, source_id))
    for table, column in (("supply_chain_relations", "supplier_org_id"), ("supply_chain_relations", "customer_org_id"),
                          ("organizations", "parent_org_id")):
        cursor.execute(f"UPDATE {table} SET {column} = %s WHERE {column} = %s", (target_id, source_id))
    cursor.execute("DELETE FROM organizations WHERE org_id = %s", (source_id,))
    cursor.execute("INSERT IGNORE INTO organization_aliases (alias, org_id, source) VALUES (%s, %s, 'manual')",
                   (row["canonical_name"], target_id))
