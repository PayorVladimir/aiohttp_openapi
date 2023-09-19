all: fmt tst lint
fmt:
	isort --py 38 . && black -t py38 .
lint: fmt
	flake8
test:
	pytest -v
tst:
	pytest -v --lf

clean:
	rm -rf dist && rm -rf src/*.egg-info
dist:
	python -m build && rm -rf src/*.egg-info

demo:
	adev runserver tests/demo_notes
