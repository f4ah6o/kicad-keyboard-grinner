lint:
	uvx ruff check

fmt:
	uvx black .

test:
	uvx pytest

testc:
	uvx pytest --cov=keyboard_grinner
