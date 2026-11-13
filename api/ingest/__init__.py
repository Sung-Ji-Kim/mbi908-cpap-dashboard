import azure.functions as func
from shared import cpap


def main(req: func.HttpRequest) -> func.HttpResponse:
    return cpap.ingest(req)
