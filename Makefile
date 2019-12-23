.PHONY: test build-assets publish-assets clean

test:
	python3 -m venv --clear venv
	venv/bin/pip install pytest .
	venv/bin/pytest -s

build-assets:
	rm -rf dist/
	python3 -m venv --clear venv
	venv/bin/python setup.py sdist

publish-assets:
	make build-assets
	venv/bin/pip install twine
	venv/bin/twine upload dist/*

clean:
	git clean -fdX
