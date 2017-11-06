.PHONY: all
all:
	python generate_lists.py --cascade --csv --xls --kml
	python generate_lists.py --csv --xls --kml
