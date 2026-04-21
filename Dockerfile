FROM python:3.12-slim

WORKDIR /app

# Install build deps needed for wheels (matplotlib / scipy / statsmodels)
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
COPY examples /app/examples
COPY streamlit_app.py /app/

# Install core + ui + serve extras. Benchling SDK stays opt-in.
RUN pip install --no-cache-dir -e '.[ui,serve]'

EXPOSE 8501 8000

# Default: Streamlit on :8501. Override with `docker run … screenase serve` etc.
CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
