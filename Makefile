.PHONY: all
all:
	python generate_lists.py --cascade --csv --xls
	python generate_lists.py --csv --xls
