#!/usr/bin/env python3
"""Mirror the variables of the I-ADOPT space from the nanopub network into this repository.

For every nanopublication that LIST_URL returns (the current, not retracted or superseded,
variables that the I-ADOPT space page lists), the script keeps two files in OUT_DIR, both named
after the nanopublication's artifact code:

  <code>.ttl   the assertion graph as plain Turtle, which the catalogue builds its pages from
  <code>.trig  the complete signed nanopublication, as published

A nanopublication never changes, so a file that exists is never fetched again; only new
nanopublications are downloaded, and the files of those that the list no longer contains
(because they were retracted or superseded, or the list itself changed) are removed.

Requires rdflib (pip install rdflib).
"""

import csv
import io
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from rdflib import RDF, Dataset, Graph, Literal, URIRef
from rdflib.namespace import Namespace

# The variables of the I-ADOPT space: the query of the "I-ADOPT LLM Service Variables" view on
# https://nanodash.knowledgepixels.com/space?id=https://w3id.org/spaces/I-ADOPT, which lists the
# current variables published by the I-ADOPT LLM Service. The script runs the latest version of
# this query, following its npx:supersedes chain, so a new version of the query is picked up
# without changing anything here. Only its "np" column is used, so any query with such a column
# works; if the space page gets a different variable query, put that one here.
LIST_QUERY_NP = "https://w3id.org/np/RAtgmu16tM9HfgVvPk_C3cXLjDe1J9mbtBGHhDJYOQdQE"

# The router redirects to a query instance or registry that is currently up.
API_URL = "https://router.knowledgepixels.com/query/api/{code}/{name}.csv"
# The latest version of a nanopublication along its supersedes chain (columns latest, date).
LATEST_VERSION_URL = API_URL.format(code="RAiRsB2YywxjsBMkVRTREJBooXhf2ZOHoUs5lxciEl37I",
                                    name="get-latest-version-of-np") + "?np={np}"
# A single nanopublication as TriG.
NANOPUB_URL = "https://router.knowledgepixels.com/registry/np/{code}.trig"

OUT_DIR = Path(__file__).resolve().parent.parent / "Nanopublications"

# Refuse to delete files when the list has shrunk by more than this fraction since the last run,
# and by more than MAX_REMOVE_ANYWAY variables: a query instance that is still loading can
# answer with an incomplete list. To switch to a query with a much smaller list, delete the files
# that are no longer wanted in the same commit.
MAX_SHRINK = 0.2
MAX_REMOVE_ANYWAY = 5

NP = Namespace("http://www.nanopub.org/nschema#")
GRLC_QUERY = URIRef("https://w3id.org/kpxl/grlc/grlc-query")
IOP = Namespace("https://w3id.org/iadopt/ont/")
COMPONENT_PREDICATES = [IOP.hasProperty, IOP.hasObjectOfInterest, IOP.hasMatrix,
                        IOP.hasContextObject, IOP.hasStatisticalModifier, IOP.hasConstraint,
                        IOP.constrains]

# Prefixes for the Turtle files, as the hand-written I-ADOPT files use them; many nanopubs
# declare none for these namespaces.
PREFIXES = {
    "iop": "https://w3id.org/iadopt/ont/",
    "iopp": "https://w3id.org/iadopt/pattern/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "dcterms": "http://purl.org/dc/terms/",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "prov": "http://www.w3.org/ns/prov#",
    "sosa": "http://www.w3.org/ns/sosa/",
}
USER_AGENT = "iadopt-catalogue-export"


def fetch(url, accept, attempts=4):
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8")
        except Exception as e:
            if attempt == attempts:
                raise
            print(f"  retry {attempt} for {url}: {e}", file=sys.stderr)
            time.sleep(5 * attempt)


def fetch_csv(url):
    return list(csv.DictReader(io.StringIO(fetch(url, "text/csv"))))


def artifact_code(uri):
    code = uri.strip().rstrip("/").rsplit("/", 1)[-1]
    return code if code.startswith("RA") and len(code) == 45 else None


def latest_version(np_uri):
    """Return the latest version of a nanopublication, or the nanopublication itself if the
    latest version cannot be determined (e.g. because its chain has forked into two heads)."""
    try:
        rows = fetch_csv(LATEST_VERSION_URL.format(np=urllib.parse.quote(np_uri, safe="")))
    except Exception as e:
        print(f"  could not look up the latest version of {np_uri}: {e}", file=sys.stderr)
        return np_uri
    heads = {row["latest"].strip() for row in rows if artifact_code(row["latest"])}
    if len(heads) != 1:
        print(f"  found {len(heads)} latest versions of {np_uri}; using it as it is",
              file=sys.stderr)
        return np_uri
    return heads.pop()


def list_url():
    """Return the API URL of the latest version of the list query."""
    code = artifact_code(latest_version(LIST_QUERY_NP))
    _, assertion = assertion_graph(fetch(NANOPUB_URL.format(code=code), "application/trig"))
    queries = set(assertion.subjects(RDF.type, GRLC_QUERY))
    if len(queries) != 1:
        sys.exit(f"Nanopublication {code} defines {len(queries)} queries instead of one.")
    return API_URL.format(code=code, name=str(queries.pop()).rsplit("/", 1)[-1])


def list_nanopubs():
    url = list_url()
    print(f"Variables listed by {url}")
    codes = {}
    for row in fetch_csv(url):
        code = artifact_code(row["np"])
        if code:
            codes[code] = row["np"].strip()
    return codes


def text_components(ttl):
    """Return the components given as plain text where I-ADOPT expects an entity.

    The catalogue turns every component into a link, and a link made from a text value points
    to a page that does not exist, which fails the whole build.
    """
    graph = Graph().parse(data=ttl, format="turtle")
    return [f"{p.split('/')[-1]} \"{o}\"" for p in COMPONENT_PREDICATES
            for o in graph.objects(None, p) if isinstance(o, Literal)]


def assertion_graph(trig):
    """Return the parsed nanopublication and its assertion graph."""
    ds = Dataset()
    ds.parse(data=trig, format="trig")
    assertion = None
    for graph in ds.graphs():
        for _, _, a in graph.triples((None, NP.hasAssertion, None)):
            assertion = a
    if not isinstance(assertion, URIRef):
        raise ValueError("no assertion graph found")
    return ds, ds.graph(assertion)


def assertion_turtle(trig):
    ds, assertion = assertion_graph(trig)
    out = Graph()
    for prefix, namespace in PREFIXES.items():
        out.bind(prefix, namespace, override=True, replace=True)
    for prefix, namespace in ds.namespaces():
        # skip the names rdflib makes up (ns1, ns2, ...) and the nanopub's own prefixes
        if re.fullmatch(r"ns\d+", prefix) or prefix in ("", "this", "np", "npx", "nt"):
            continue
        out.bind(prefix, namespace, override=False)
    for triple in assertion:
        out.add(triple)
    if len(out) == 0:
        raise ValueError("assertion graph is empty")
    return out.serialize(format="turtle")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    current = list_nanopubs()
    if not current:
        sys.exit("The query returned no nanopublications; leaving the files as they are.")

    existing = {p.stem for p in OUT_DIR.glob("*.ttl")} | {p.stem for p in OUT_DIR.glob("*.trig")}
    gone = existing - set(current)
    if len(gone) > max(MAX_REMOVE_ANYWAY, MAX_SHRINK * len(existing)):
        sys.exit(f"The list would remove {len(gone)} of {len(existing)} variables; "
                 "this looks like an incomplete answer, so nothing is changed.")

    added, skipped, failed = 0, 0, 0
    for code in sorted(current):
        ttl_file, trig_file = OUT_DIR / f"{code}.ttl", OUT_DIR / f"{code}.trig"
        if ttl_file.exists() and trig_file.exists():
            continue
        try:
            # a .ttl file that is missing is made again from the saved nanopub
            if trig_file.exists():
                trig = trig_file.read_text(encoding="utf-8")
            else:
                trig = fetch(NANOPUB_URL.format(code=code), "application/trig")
            ttl = assertion_turtle(trig)
        except Exception as e:
            print(f"  could not export {code}: {e}", file=sys.stderr)
            failed += 1
            continue
        trig_file.write_text(trig, encoding="utf-8")
        problems = text_components(ttl)
        if problems:
            # keep the nanopub, but leave it out of the catalogue
            print(f"  not in the catalogue: {code} ({', '.join(problems)})")
            skipped += 1
            continue
        ttl_file.write_text(ttl, encoding="utf-8")
        added += 1

    for code in sorted(gone):
        for suffix in (".ttl", ".trig"):
            (OUT_DIR / f"{code}{suffix}").unlink(missing_ok=True)

    print(f"{len(current)} current nanopublications: {added} written, {skipped} left out of the "
          f"catalogue, {len(gone)} removed, {failed} failed.")
    if failed:
        print("The failed ones are tried again on the next run.")


if __name__ == "__main__":
    main()
