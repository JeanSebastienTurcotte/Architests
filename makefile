# Makefile 
# Pas utilisé en ce moment

PYTHON=python
BUILDER=builder.py
OUTPUT_DIR=output

all: quiz

quiz:
	$(PYTHON) $(BUILDER) --questions all --versions 1 --solutions --seed 1234

student:
	$(PYTHON) $(BUILDER) --questions all --versions 1 --seed 1234

multi:
	$(PYTHON) $(BUILDER) --questions all --versions 3 --shuffle --seed 2025

clean:
	rm -f $(OUTPUT_DIR)/*.aux $(OUTPUT_DIR)/*.log $(OUTPUT_DIR)/*.fls \
	      $(OUTPUT_DIR)/*.fdb_latexmk $(OUTPUT_DIR)/*.out

distclean: clean
	rm -f $(OUTPUT_DIR)/*.pdf $(OUTPUT_DIR)/*.tex $(OUTPUT_DIR)/fig_*.pdf
