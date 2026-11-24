# Healthcare Operations Cost Analysis - pipeline entry points.
#   make setup      create .venv (Python 3.11) and install pinned requirements
#   make ingest     download the CMS source files into data/raw/
#   make transform  build DuckDB staging + analytical tables and run data quality checks
#   make analyze    run statistics, write figures, findings inputs, Power BI CSVs, notebook
#   make all        ingest + transform + analyze

PYTHON_BIN ?= python3.11
VENV       := .venv
PY         := $(VENV)/bin/python

.PHONY: setup ingest transform analyze notebook all clean

setup:
	$(PYTHON_BIN) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

ingest:
	$(PY) python/ingest.py

transform:
	$(PY) python/transform.py

analyze:
	$(PY) python/analysis.py
	$(MAKE) notebook

notebook:
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb

all: ingest transform analyze

clean:
	rm -f data/*.duckdb data/*.duckdb.wal
