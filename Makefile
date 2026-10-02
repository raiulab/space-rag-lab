.PHONY: install all test api clean-generated

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e .

all:
	PYTHONPATH=src python3 -m rag_lab.cli all

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

api:
	.venv/bin/uvicorn rag_lab.api:app --reload

clean-generated:
	@echo "生成物を削除する場合は data/processed、data/index、reports を確認して手動で削除してください。"
