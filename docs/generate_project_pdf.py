from pathlib import Path
import textwrap

from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "Identity_Search_Service_Client_Explanation.md"
OUTPUT = ROOT / "Identity_Search_Service_Client_Explanation.pdf"


def classify_line(line):
    if line.startswith("# "):
        return "title", line[2:].strip()
    if line.startswith("## "):
        return "heading", line[3:].strip()
    if line.startswith("### "):
        return "subheading", line[4:].strip()
    if line.startswith("- "):
        return "bullet", line[2:].strip()
    return "body", line


def add_page(pdf, lines, page_number):
    fig = plt.figure(figsize=(8.27, 11.69))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    y = 0.955
    for kind, text in lines:
        if kind == "title":
            ax.text(0.08, y, text, fontsize=20, fontweight="bold", va="top")
            y -= 0.045
        elif kind == "heading":
            ax.text(0.08, y, text, fontsize=14, fontweight="bold", va="top", color="#12355b")
            y -= 0.031
        elif kind == "subheading":
            ax.text(0.08, y, text, fontsize=12, fontweight="bold", va="top")
            y -= 0.027
        elif kind == "bullet":
            ax.text(0.095, y, f"- {text}", fontsize=9.2, va="top", family="DejaVu Sans")
            y -= 0.019
        elif kind == "code":
            ax.text(0.10, y, text, fontsize=8.5, va="top", family="DejaVu Sans Mono", color="#222222")
            y -= 0.017
        else:
            ax.text(0.08, y, text, fontsize=9.4, va="top", family="DejaVu Sans")
            y -= 0.018

    ax.text(0.5, 0.035, f"Identity Search And Document Verification System | Page {page_number}",
            fontsize=8, ha="center", color="#666666")
    pdf.savefig(fig)
    plt.close(fig)


def build_flowables(markdown_text):
    flowables = []
    in_code = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            in_code = not in_code
            continue

        if not line:
            flowables.append(("space", ""))
            continue

        if in_code:
            wrapped = textwrap.wrap(line, width=82, replace_whitespace=False) or [""]
            for item in wrapped:
                flowables.append(("code", item))
            continue

        kind, text = classify_line(line)

        if kind in {"title", "heading", "subheading"}:
            flowables.append((kind, text))
            continue

        width = 92 if kind == "bullet" else 95
        wrapped = textwrap.wrap(text, width=width, replace_whitespace=False) or [""]

        for index, item in enumerate(wrapped):
            if kind == "bullet":
                flowables.append(("bullet" if index == 0 else "body", item if index == 0 else f"  {item}"))
            else:
                flowables.append((kind, item))

    return flowables


def paginate(flowables):
    pages = []
    current = []
    used = 0.0

    heights = {
        "title": 2.8,
        "heading": 2.0,
        "subheading": 1.7,
        "bullet": 1.15,
        "code": 1.0,
        "body": 1.05,
        "space": 0.65,
    }
    page_limit = 52.0

    for kind, text in flowables:
        height = heights.get(kind, 1.0)

        if current and used + height > page_limit:
            pages.append(current)
            current = []
            used = 0.0

        if kind == "space":
            current.append(("body", ""))
        else:
            current.append((kind, text))

        used += height

    if current:
        pages.append(current)

    return pages


def main():
    markdown_text = SOURCE.read_text(encoding="utf-8")
    flowables = build_flowables(markdown_text)
    pages = paginate(flowables)

    with PdfPages(OUTPUT) as pdf:
        for index, page in enumerate(pages, start=1):
            add_page(pdf, page, index)

    print(OUTPUT)


if __name__ == "__main__":
    main()
