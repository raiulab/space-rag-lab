"""Regenerate the repository-owned PDF fixture.

Run this script with a Python environment that provides ReportLab. The generated
document contains only synthetic text written for this project.
"""

from pathlib import Path

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


OUTPUT = Path(__file__).with_name("lab1_text_sample.pdf")


def main() -> None:
    font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    pdfmetrics.registerFont(TTFont("FixtureSans", font_path))
    document = canvas.Canvas(str(OUTPUT), pagesize=(595, 842))
    document.setTitle("Lab 1 PDF取り込みテスト")
    document.setAuthor("Space RAG Lab")
    document.setFont("FixtureSans", 15)
    document.drawString(72, 770, "Mars Power System Test Report")
    document.setFont("FixtureSans", 11)
    document.drawString(
        72, 735, "During the peak dust storm, solar-array output fell to 32% of normal."
    )
    document.drawString(
        72, 710, "Battery storage and load control maintained power to critical equipment."
    )
    document.showPage()

    document.setFont("FixtureSans", 15)
    document.drawString(72, 770, "Communications Test")
    document.setFont("FixtureSans", 11)
    document.drawString(
        72, 735, "Retransmission control stayed within limits during simulated delay."
    )
    document.drawString(
        72, 710, "Unicode extraction check: temperature 78°C, efficiency 95%."
    )
    document.showPage()

    # Page 3 is intentionally blank so ingestion can exercise its warning path.
    document.showPage()
    document.save()


if __name__ == "__main__":
    main()
