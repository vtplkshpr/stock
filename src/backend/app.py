"""HTTP API for the company diagram, plus the built frontend (src/frontend/dist) on the same origin."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, partners, sections
from .config import FRONTEND_DIST, Settings
from .sections import Company

RESERVED_PARAMS = {"page", "page_size"}


def clean(value: Any) -> Any:
    """Make query results JSON-friendly: exact decimals become numbers, dates ISO strings."""
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


def ok(payload: Any) -> JSONResponse:
    return JSONResponse(clean(payload))


def company_or_404(ref: str) -> Company:
    """Resolve an entity reference: a ticker, or "org:<id>" for an organisation of the register
    (a listed organisation resolves to its company)."""
    ref = ref.strip()
    if ref.lower().startswith("org:") and ref[4:].isdigit():
        org = db.one("SELECT org_id, canonical_name, ticker FROM organizations WHERE org_id = %(id)s",
                     {"id": int(ref[4:])})
        if org is None:
            raise HTTPException(404, f"Organisation {ref} is not in the database.")
        if not org["ticker"]:
            return Company(None, None, org["canonical_name"], org["org_id"])
        ref = org["ticker"]
    row = db.one("""SELECT c.company_id, c.ticker, c.company_name, o.org_id FROM companies AS c
                    LEFT JOIN organizations AS o ON o.ticker = c.ticker
                    WHERE c.ticker = %(t)s LIMIT 1""", {"t": ref.upper()})
    if row is None:
        raise HTTPException(404, f"Ticker {ref} is not in the database.")
    return Company(row["company_id"], row["ticker"], row["company_name"], row["org_id"])


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Stock company diagram API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["GET"], allow_headers=["*"])

    @app.exception_handler(db.Error)
    async def database_error(request: Request, exc: db.Error) -> JSONResponse:
        return JSONResponse({"detail": f"Database error: {exc}"}, status_code=503)

    @app.get("/api/health")
    def health() -> JSONResponse:
        db.check_connection()
        return ok({"status": "ok"})

    @app.get("/api/companies/search")
    def search(q: str = Query("", max_length=100), limit: int = Query(20, ge=1, le=50)) -> JSONResponse:
        text = q.strip()
        if not text:
            return ok([])
        found = db.rows(
            """SELECT c.ticker, c.company_name, c.exchange,
                      (EXISTS (SELECT 1 FROM finance_reports f WHERE f.company_id = c.company_id)
                       OR EXISTS (SELECT 1 FROM stock_prices p WHERE p.company_id = c.company_id)
                       OR EXISTS (SELECT 1 FROM related_party_transactions r
                                  WHERE r.company_id = c.company_id)
                       OR EXISTS (SELECT 1 FROM foreign_trades t WHERE t.company_id = c.company_id)
                       OR EXISTS (SELECT 1 FROM insider_trades t WHERE t.company_id = c.company_id)
                       OR EXISTS (SELECT 1 FROM intraday_trades t WHERE t.company_id = c.company_id)
                       OR EXISTS (SELECT 1 FROM stock_holders h WHERE h.company_id = c.company_id))
                      AS has_data
               FROM companies AS c
               WHERE c.ticker LIKE %(prefix)s OR c.company_name LIKE %(contains)s
               ORDER BY c.ticker = %(exact)s DESC, has_data DESC, c.ticker LIKE %(prefix)s DESC,
                        CHAR_LENGTH(c.ticker), c.ticker
               LIMIT %(limit)s""",
            {"prefix": f"{text.upper()}%", "contains": f"%{text}%", "exact": text.upper(), "limit": limit},
        )
        for row in found:
            row["has_data"] = bool(row["has_data"])
            row["ref"] = row["ticker"]
        # Unlisted organisations of the register, by canonical name or any recorded spelling.
        organisations = db.rows(
            """SELECT o.org_id, o.canonical_name, o.kind, o.legal_form FROM organizations AS o
               WHERE o.ticker IS NULL AND (o.canonical_name LIKE %(contains)s OR EXISTS (
                   SELECT 1 FROM organization_aliases AS a
                   WHERE a.org_id = o.org_id AND a.alias LIKE %(contains)s COLLATE utf8mb4_unicode_ci))
               ORDER BY CHAR_LENGTH(o.canonical_name) LIMIT %(limit)s""",
            {"contains": f"%{text}%", "limit": max(0, limit - len(found))})
        found += [{"ref": f"org:{o['org_id']}", "ticker": None, "company_name": o["canonical_name"],
                   "exchange": None, "kind": o["kind"], "has_data": True} for o in organisations]
        return ok(found)

    @app.get("/api/companies/featured")
    def featured(limit: int = Query(12, ge=1, le=50)) -> JSONResponse:
        """Companies that hold detailed data, richest first (suggestions on the start screen)."""
        rows = db.rows(
            """SELECT c.ticker, c.company_name, c.exchange, TRUE AS has_data
               FROM companies AS c
               JOIN (SELECT company_id, COUNT(DISTINCT source) AS kinds, COUNT(*) AS n FROM (
                         SELECT company_id, 'reports' AS source FROM finance_report_items
                         UNION ALL SELECT company_id, 'related' FROM related_party_transactions
                         UNION ALL SELECT company_id, 'prices' FROM stock_prices
                         UNION ALL SELECT company_id, 'insiders' FROM insider_trades
                         UNION ALL SELECT company_id, 'intraday' FROM intraday_trades
                         UNION ALL SELECT company_id, 'holders' FROM stock_holders
                         UNION ALL SELECT company_id, 'leaders' FROM company_leaders) AS everything
                     GROUP BY company_id) AS data USING (company_id)
               ORDER BY data.kinds DESC, data.n DESC LIMIT %(limit)s""", {"limit": limit})
        return ok([{**row, "ref": row["ticker"]} for row in rows])

    @app.get("/api/companies/{ticker}")
    def company(ticker: str) -> JSONResponse:
        found = company_or_404(ticker)
        row = db.one("SELECT exchange, industry FROM companies WHERE company_id = %(cid)s",
                     {"cid": found.company_id}) or {}
        org = db.one("SELECT kind, legal_form, full_name, industry FROM organizations WHERE org_id = %(oid)s",
                     {"oid": found.org_id}) or {}
        price = db.one("""SELECT price_date, close_price, change_percentage FROM stock_prices
                          WHERE company_id = %(cid)s ORDER BY price_date DESC LIMIT 1""",
                       {"cid": found.company_id})
        return ok({
            "ref": found.ref, "entity": "company" if found.listed else "organization",
            "ticker": found.ticker, "name": found.name, "exchange": row.get("exchange"),
            "industry": row.get("industry") or org.get("industry"), "price": price,
            "kind": org.get("kind"), "legal_form": org.get("legal_form"), "full_name": org.get("full_name"),
            "sections": sections.describe(found),
            "partners": {side: len(partners.summary(found, side)) for side in partners.SIDES},
        })

    @app.get("/api/companies/{ticker}/sections/{key}")
    def section(ticker: str, key: str, request: Request, page: int = Query(1, ge=1),
                page_size: int = Query(10, ge=1, le=500)) -> JSONResponse:
        found = company_or_404(ticker)
        entry = sections.BY_KEY.get(key)
        if entry is None or entry.fetch is None:
            raise HTTPException(404, f"Unknown section {key}.")
        options = {k: v for k, v in request.query_params.items() if k not in RESERVED_PARAMS}
        return ok({"key": key, **entry.fetch(found, options, page, page_size)})

    @app.get("/api/companies/{ticker}/partners")
    def partner_list(ticker: str, side: str = Query(..., pattern="^(suppliers|customers)$"),
                     offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100)) -> JSONResponse:
        found = company_or_404(ticker)
        listed = partners.summary(found, side)
        return ok({"side": side, "total": len(listed), "offset": offset,
                   "items": listed[offset:offset + limit]})

    @app.get("/api/companies/{ticker}/partner-transactions")
    def partner_transactions(ticker: str, key: str = Query(..., min_length=3),
                             side: str = Query(..., pattern="^(suppliers|customers)$")) -> JSONResponse:
        return ok(partners.transactions(company_or_404(ticker), side, key))

    @app.get("/api/news/{news_id}")
    def news(news_id: int) -> JSONResponse:
        row = db.one("""SELECT n.title, n.content_text, n.media_type, n.media_url, n.published_at,
                               n.source_name, n.source_url, c.ticker
                        FROM company_news AS n JOIN companies AS c USING (company_id)
                        WHERE n.news_id = %(id)s""", {"id": news_id})
        if row is None:
            raise HTTPException(404, "News item not found.")
        return ok(row)

    @app.get("/api/{rest:path}")
    def unknown_api(rest: str) -> JSONResponse:
        return JSONResponse({"detail": "Not found."}, status_code=404)

    mount_frontend(app)
    return app


def mount_frontend(app: FastAPI) -> None:
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        @app.get("/{rest:path}", response_class=HTMLResponse)
        def not_built(rest: str = "") -> str:
            return ("<h2>The diagram frontend has not been built.</h2>"
                    "<p>Run <code>bash scripts/setup_web.sh</code>, then restart the server.</p>"
                    "<p>The API is available at <a href='/api/docs'>/api/docs</a>.</p>")
        return

    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{rest:path}")
    def spa(rest: str = "") -> FileResponse:
        candidate = (FRONTEND_DIST / rest).resolve()
        if rest and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
