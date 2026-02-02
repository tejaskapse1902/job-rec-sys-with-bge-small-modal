Python version: 3.10.x
Steps:
1. python -m venv venv
2. activate venv
3. pip install -r requirements.txt
4. pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl
5. python tools/build_faiss_index.py
6. uvicorn app.main:app --reload
