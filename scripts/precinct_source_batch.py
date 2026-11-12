"""Batch a public precinct-source directory without mistaking links for observations."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import html
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sys
import threading
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.house_clerk_endpoints import STATES
from scripts.participation_intake.contract import IntakeError, digest, encoded, pin
from scripts.participation_intake.engine import Store


DIRECTORY = "https://redistrictingdatahub.org/resources/precinct-level-data-sources/"
COLUMNS = {"State", "Precinct Boundaries / Maps", "Precinct-Level Election Results"}
KINDS = {"boundaries": "Precinct Boundaries / Maps", "results": "Precinct-Level Election Results"}
STATE_CODES = {name: code for code, name in STATES.items()}
STATE_CODES["District of Columbia"] = "DC"


def normalized_url(value):
    parsed = urlsplit(value.strip())
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def registry(body, require_complete=True):
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""))
    if set(reader.fieldnames or []) != COLUMNS or len(reader.fieldnames or []) != len(COLUMNS):
        raise ValueError("Unexpected source-directory columns")
    rows, seen = [], set()
    for number, source in enumerate(reader, 2):
        state = (source.get("State") or "").strip()
        if None in source or any(value is None for value in source.values()) or state not in STATE_CODES or state in seen:
            raise ValueError("Unknown, duplicate or incomplete jurisdiction at CSV row "+str(number))
        seen.add(state)
        products = {}
        for kind, column in KINDS.items():
            literal = source[column]
            value = literal.strip()
            parsed = urlsplit(value)
            url = normalized_url(value) if parsed.scheme in ("https", "http") and parsed.netloc else None
            status = "directory_link_unverified" if url else (
                "not_listed_in_directory" if value == "Not available from state" else "manual_request_not_followed")
            qualifications = []
            if url and parsed.scheme != "https":
                status = "non_https_link_requires_review"
            if kind == "results" and url and "/redistricting/" in parsed.path.lower():
                status = "wrong_product_link_requires_review"
                qualifications.append("Directory results link points to redistricting/GIS, not a verified election-results export.")
            if kind == "boundaries":
                qualifications.append("Boundary vintage and election-specific joins remain unqualified.")
            else:
                qualifications.append("Candidate results do not establish ballots cast, registration or turnout.")
            products[kind] = dict(literal=literal, url=url, status=status,
                directory_is_not_acquisition=True, election_year_verified=False,
                numerical_counts_available=False, qualifications=qualifications)
        rows.append(dict(state_code=STATE_CODES[state], state=state, products=products))
    if require_complete and seen != set(STATE_CODES):
        raise ValueError("The complete 50-state-plus-DC directory is required")
    return sorted(rows, key=lambda row: row["state_code"])


def ledger_holds(text):
    stopped = set()
    blocks=[]
    for paragraph in text.split("\n\n"):
        if any(line.lstrip().startswith("|") for line in paragraph.splitlines()):
            blocks.extend(paragraph.splitlines())
        else:
            blocks.append(paragraph)
    for block in blocks:
        if not (re.search(r"\b(?:401|403|429)\b|security challenge", block, re.I)
                and re.search(r"stop|denied|blocked|no retry|not retried", block, re.I)):
            continue
        for value in re.findall(r"https?://[^\s<>`]+", block):
            value = value.rstrip(".,;:)")
            if "](" in value:
                continue
            stopped.add(normalized_url(html.unescape(value)))
    return stopped


class Links(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.links, self.current = base, [], None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.current = dict(url=urljoin(self.base, href.strip()), text="")

    def handle_data(self, value):
        if self.current:
            self.current["text"] += value

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            self.current["text"] = " ".join(self.current["text"].split())
            self.links.append(self.current)
            self.current = None


def discover_links(body, base, year):
    parser = Links(base)
    parser.feed(body.decode("utf-8", errors="replace"))
    candidates = {}
    for link in parser.links:
        parsed = urlsplit(link["url"])
        if parsed.scheme != "https":
            continue
        context = link["text"]+" "+parsed.path+" "+parsed.query
        if not re.search(r"(?<![0-9])"+str(year)+r"(?![0-9])", context):
            continue
        if re.search(r"\bprimary\b|\bspecial\b|\brunoff\b", context, re.I) and not re.search(r"\bgeneral\b", context, re.I):
            continue
        extension = Path(parsed.path).suffix.lower()
        role = "download_candidate" if extension in {".csv", ".txt", ".json", ".zip", ".xlsx", ".xls", ".pdf"} else "election_index_candidate"
        key = normalized_url(link["url"])
        candidates[key] = dict(link, url=key, role=role,
            election_scope_verified=False, numerical_data_qualified=False,
            ballots_cast_not_inferred_from_candidate_votes=True)
    return sorted(candidates.values(), key=lambda row: row["url"])


def fetch_index(store, url, stopped, refresh=False):
    url = normalized_url(url)
    if url in stopped:
        return dict(url=url, status="ledger_access_hold_not_followed", acquired=False, source_requests=0)
    existing = store.db.execute("SELECT sha,stopped FROM inputs WHERE url=?", (url,)).fetchone()
    if existing and existing[1]:
        return dict(url=url, status="persistent_source_stop_not_followed", acquired=False, source_requests=0)
    if existing and existing[0] and not refresh:
        body = (store.root/"objects"/existing[0]).read_bytes()
        if digest(body) != existing[0]:
            raise ValueError("Previously acquired source-index bytes changed")
        return dict(url=url, status="cached_original", acquired=True, source_requests=0, **pin(body))
    description = dict(url=url, reject_body_patterns=[
        r"verify (?:that )?you are human", r"cf-chl-", r"incapsula incident id", r"captcha challenge"])
    try:
        body, receipt = store.acquire(description)
    except IntakeError as error:
        return dict(url=url, status="source_not_acquired", acquired=False,
            source_requests=0 if error.code == "source_url" else 1, error=error.as_dict())
    return dict(url=url, status="source_index_acquired", acquired=True,
                source_requests=1, **pin(body), origin=receipt["origin"])


def collect(directory, cache, output, year, ledger="", fetch=False, refresh=False, kinds=("results",)):
    body = Path(directory).read_bytes()
    rows = registry(body)
    years = sorted(set([year] if isinstance(year, int) else year), reverse=True)
    if not years or any(type(value) is not int or value < 1788 or value > 2100 for value in years):
        raise ValueError("Select explicit election years")
    stopped = ledger_holds(ledger)
    settings = dict(directory=pin(body), years=years, kinds=list(kinds), fetch_indexes=fetch,
                    stopped_urls=sorted(stopped), code=pin(Path(__file__).read_bytes()))
    recipe = digest(encoded(settings))
    output = Path(output)
    if output.exists():
        manifest = json.loads((output/"manifest.json").read_bytes())
        if manifest["recipe"] != recipe or refresh:
            raise ValueError("Use a fresh output for changed inputs or an explicit source refresh")
        for name, expected in manifest["files"].items():
            if pin((output/name).read_bytes()) != expected:
                raise ValueError("Cached complete directory output changed")
        return dict(status="unchanged", recipe=recipe, source_requests=0,
                    source_parses=0, directory=str(output))
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    context = threading.local()

    def acquire(url):
        if not hasattr(context, "store"):
            context.store = Store(cache)
        return fetch_index(context.store, url, stopped, refresh)

    urls = sorted({row["products"][kind]["url"] for row in rows for kind in kinds
                   if row["products"][kind]["status"] == "directory_link_unverified"})
    receipts = {}
    if fetch:
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = {item["url"]: item for item in pool.map(acquire, urls)}
    for row in rows:
        for kind, product in row["products"].items():
            receipt = receipts.get(product["url"])
            if receipt:
                product["acquisition"] = receipt
                if receipt["acquired"]:
                    original = (cache/"objects"/receipt["sha256"]).read_bytes()
                    product["linked_candidates_by_year"] = {
                        str(value):discover_links(original, product["url"], value) for value in years}
    output.mkdir(parents=True)
    (output/"original-directory.csv").write_bytes(body)
    (output/"complete-jurisdiction-query.json").write_bytes(encoded(rows))
    (output/"source-access-holds.json").write_bytes(encoded(sorted(stopped)))
    for receipt in receipts.values():
        if receipt["acquired"]:
            target = output/"original-indexes"/receipt["sha256"]
            target.parent.mkdir(exist_ok=True)
            target.write_bytes((cache/"objects"/receipt["sha256"]).read_bytes())
    summary = dict(status="source_directory_batch_collected_not_qualified_election_data",
        recipe=recipe, jurisdictions=len(rows), election_years=years, source_index_urls=len(urls),
        source_requests=sum(value["source_requests"] for value in receipts.values()),
        acquired_source_indexes=sum(value["acquired"] for value in receipts.values()),
        cached_source_indexes=sum(value["status"] == "cached_original" for value in receipts.values()),
        source_holds=sum(not value["acquired"] for value in receipts.values()),
        registered_products={kind:sum(row["products"][kind]["url"] is not None for row in rows) for kind in KINDS},
        original_directory_retained=True, every_jurisdiction_and_hold_retained=True,
        new_qualified_ballot_observations=0, new_qualified_candidate_observations=0,
        precinct_geometry_joins_qualified=0, directory_does_not_prove_2026_availability=True,
        paid_requests_accounts_or_official_contacts_started=0)
    (output/"summary.json").write_bytes(encoded(summary))
    manifest = dict(recipe=recipe, source_directory=DIRECTORY, settings=settings,
        files={str(path.relative_to(output)):pin(path.read_bytes())
               for path in sorted(output.rglob("*")) if path.is_file()})
    (output/"manifest.json").write_bytes(encoded(manifest))
    return dict(summary, directory=str(output))


def is_general_precinct_product(link, year):
    name = unquote(Path(urlsplit(link["url"]).path).name).replace("_", " ")
    if str(year) not in name or re.search(r"primary|runoff|special", name, re.I):
        return False
    if not re.search("general", name, re.I):
        return False
    return bool(re.search("precinct", name, re.I) or
                re.search(r"ElectionReturns.*ReadMe", name, re.I))


def collect_products(collection, cache, output, years, states, ledger=""):
    collection, output = Path(collection), Path(output)
    original = (collection/"complete-jurisdiction-query.json").read_bytes()
    previous = json.loads((collection/"manifest.json").read_bytes())
    if pin(original) != previous["files"]["complete-jurisdiction-query.json"]:
        raise ValueError("Source-directory query differs from its manifest")
    rows = json.loads(original)
    selected = []
    for row in rows:
        if row["state_code"] not in states:
            continue
        product = row["products"]["results"]
        for year in years:
            for link in product.get("linked_candidates_by_year", {}).get(str(year), []):
                if link["role"] == "download_candidate" and is_general_precinct_product(link, year):
                    selected.append(dict(link, state_code=row["state_code"], year=year,
                        declared_by=product["url"], index_sha256=product["acquisition"]["sha256"]))
    stopped = ledger_holds(ledger)
    settings = dict(index_query=pin(original), selected=selected, stopped_urls=sorted(stopped),
        code=pin(Path(__file__).read_bytes()))
    recipe = digest(encoded(settings))
    if output.exists():
        manifest = json.loads((output/"manifest.json").read_bytes())
        if manifest["recipe"] != recipe:
            raise ValueError("Changed product selection needs a new output")
        for name, expected in manifest["files"].items():
            if pin((output/name).read_bytes()) != expected:
                raise ValueError("Held product collection changed")
        return dict(status="unchanged", source_requests=0, source_parses=0, directory=str(output))
    local = threading.local()
    stopped_hosts, lock = set(), threading.Lock()

    def retrieve(product):
        if not hasattr(local, "store"):
            local.store = Store(cache)
        host = urlsplit(product["url"]).hostname
        with lock:
            held_host = host in stopped_hosts
        receipt = (dict(url=product["url"], status="host_rate_limit_hold", acquired=False, source_requests=0)
                   if held_host else fetch_index(local.store, product["url"], stopped))
        if "429" in json.dumps(receipt.get("error", {})):
            with lock:
                stopped_hosts.add(host)
        if receipt["acquired"]:
            body = (Path(cache)/"objects"/receipt["sha256"]).read_bytes()
            extension = Path(urlsplit(product["url"]).path).suffix.lower()
            if extension in (".zip", ".xlsx"):
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    bad = archive.testzip()
                    if bad:
                        raise ValueError("Original product failed ZIP CRC: "+bad)
                    receipt["zip_members"] = [dict(name=item.filename, bytes=item.file_size, crc=item.CRC)
                                             for item in archive.infolist()]
        return dict(product, acquisition=receipt)

    with ThreadPoolExecutor(max_workers=4) as pool:
        products = list(pool.map(retrieve, selected))
    output.mkdir(parents=True)
    for product in products:
        receipt = product["acquisition"]
        if receipt["acquired"]:
            target = output/"originals"/receipt["sha256"]
            target.parent.mkdir(exist_ok=True)
            target.write_bytes((Path(cache)/"objects"/receipt["sha256"]).read_bytes())
    (output/"complete-product-query.json").write_bytes(encoded(products))
    summary = dict(status="historical_products_collected_not_yet_numerically_qualified",
        selected_products=len(products), acquired_products=sum(p["acquisition"]["acquired"] for p in products),
        source_requests=sum(p["acquisition"]["source_requests"] for p in products),
        original_bytes=sum(p["acquisition"].get("bytes",0) for p in products),
        state_years=sorted({str(p["year"])+"-"+p["state_code"] for p in products}),
        numerical_qualification_and_geographic_joins_not_inferred=True)
    (output/"summary.json").write_bytes(encoded(summary))
    (output/"manifest.json").write_bytes(encoded(dict(recipe=recipe, settings=settings,
        files={str(p.relative_to(output)):pin(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()})))
    return dict(summary, directory=str(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "cache", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int)
    group.add_argument("--years", type=int, nargs="+")
    parser.add_argument("--ledger", type=Path, default=Path(__file__).resolve().parents[1]/"SOURCES.md")
    parser.add_argument("--fetch-indexes", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--kinds", nargs="+", choices=tuple(KINDS), default=["results"])
    parser.add_argument("--products-output", type=Path)
    parser.add_argument("--product-years", type=int, nargs="+")
    parser.add_argument("--product-states", nargs="+")
    args = parser.parse_args()
    if args.products_output:
        if not args.product_years or not args.product_states:
            parser.error("Product collection requires explicit --product-years and --product-states")
        result = collect_products(args.output,args.cache,args.products_output,args.product_years,
            args.product_states,args.ledger.read_text())
    else:
        result = collect(args.directory,args.cache,args.output,args.years or args.year,args.ledger.read_text(),
            args.fetch_indexes,args.refresh,tuple(args.kinds))
    print(json.dumps(result,sort_keys=True))
