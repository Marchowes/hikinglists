.PHONY: all
all: regular optimistic pessimistic

regular:
	python generate_lists.py --cascade --csv --xls --kml
	python generate_lists.py --csv --xls --kml

.PHONY: optimistic
optimistic:
	python generate_lists.py --cascade --csv --xls --kml -j
	python generate_lists.py --csv --xls --kml -j

.PHONY: pessimistic
pessimistic:
	python generate_lists.py --cascade --csv --xls --kml -l
	python generate_lists.py --csv --xls --kml -l
