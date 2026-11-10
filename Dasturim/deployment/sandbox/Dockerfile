FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib MPLBACKEND=Agg \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
RUN pip install --no-cache-dir pandas numpy matplotlib duckdb
COPY worker.py /sandbox/worker.py
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "/sandbox/worker.py"]
