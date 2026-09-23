from dataclasses import asdict
from pprint import pprint

from rag.integration import PDFParser

parser = PDFParser()
nodes = parser.parse(
    "backend/uploads/1543_Neural_Prediction_Errors_.pdf",
    paper_id="demo-paper",
)

print("节点总数：", len(nodes))

for node in nodes[:5]:
    pprint(asdict(node), sort_dicts=False)