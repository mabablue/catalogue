# catalogue

A catalogue of the I-ADOPT variables of the [I-ADOPT space](https://nanodash.knowledgepixels.com/space?id=https://w3id.org/spaces/I-ADOPT), which are published as nanopublications, built with [iadopt-catalogue](https://github.com/sirkos/iadopt-catalogue) and served on GitHub Pages.

Every night, the workflow in `.github/workflows/gh-pages.yml` runs `scripts/export_nanopubs.py`, which mirrors the variables that the space page lists into `Nanopublications/`, commits the changes, and rebuilds the site. For each nanopublication, named after its artifact code, the folder holds:

- `<code>.ttl`: the assertion graph as plain Turtle, which the catalogue pages are built from;
- `<code>.trig`: the complete signed nanopublication, as published.

Variables that are retracted or superseded, or that the space page no longer lists, are removed again.

The list comes from the query of the space page's *I-ADOPT LLM Service Variables* view, [`get-iadopt-llm-service-variables`](https://router.knowledgepixels.com/query/api/RAtgmu16tM9HfgVvPk_C3cXLjDe1J9mbtBGHhDJYOQdQE/get-iadopt-llm-service-variables.csv): the current variables published by the I-ADOPT LLM Service. The script always runs the latest version of this query, so new versions of it are picked up automatically. If the space page gets a different variable query, change `LIST_QUERY_NP` in the script. The workflow can also be started by hand under *Actions*.

To publish the site, set *Settings → Pages → Source* to *GitHub Actions*.
