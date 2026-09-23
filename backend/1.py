from pathlib import Path
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

pdf_path = Path("G:\\scholar-rag\\backend\\1543_Neural_Prediction_Errors_.pdf")

pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr = False
converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }
)
result = converter.convert(str(pdf_path))

markdown = result.document.export_to_markdown()
Path("paper.docling.md").write_text(markdown, encoding="utf-8")
