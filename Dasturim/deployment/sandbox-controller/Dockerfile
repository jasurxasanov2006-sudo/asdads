FROM docker:27-cli
RUN apk add --no-cache python3
COPY deployment/sandbox /sandbox-image
COPY deployment/sandbox-controller/controller.py /controller.py
ENV SANDBOX_IMAGE=dataflow-python-sandbox:latest
CMD ["python3", "/controller.py"]
