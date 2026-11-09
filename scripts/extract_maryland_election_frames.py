"""Read declared Maryland election-register workbooks and the card-cast report."""

import io
import re

import openpyxl
import pdfplumber


COLUMNS = dict(DEM="C", REP="E", GRN="F", OTH="G", UNA="H", WCP="I", TOTAL="K")


def read_workbook(data, status):
    first, parent = (10, 34) if status == "ACTIVE" else (9, 33)
    name = "general-eligible-" + status.lower() + ".xlsx"
    book = openpyxl.load_workbook(io.BytesIO(data), data_only=False, read_only=True)
    if len(book.sheetnames) != 1:
        raise ValueError("Changed native workbook sheet inventory")
    sheet = book.active
    header = {key: sheet[col + str(first - 1)].value for key, col in COLUMNS.items()}
    if header != {key: key for key in COLUMNS} or sheet["A" + str(first - 1)].value != "County":
        raise ValueError("Changed native registration-party columns")
    result = dict(source_file=name, status=status,
        title=sheet["B3" if status == "ACTIVE" else "B2"].value,
        election=sheet["D4" if status == "ACTIVE" else "D3"].value,
        date_label=sheet["D6" if status == "ACTIVE" else "D5"].value,
        rows=[dict(native_county_label=sheet["A" + str(row)].value, source_row=row,
            counts={key: sheet[col + str(row)].value for key, col in COLUMNS.items()},
            source_cells={key: col + str(row) for key, col in COLUMNS.items()})
            for row in range(first, parent + 1)])
    book.close()
    return result


def read_cards(data):
    with pdfplumber.open(io.BytesIO(data)) as reader:
        if len(reader.pages) != 1:
            raise ValueError("Changed native card-report page inventory")
        words = reader.pages[0].extract_words(x_tolerance=1, y_tolerance=2)
    lines = []
    for word in sorted(words, key=lambda value: (value["top"], value["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 2:
            lines.append([word])
        else:
            lines[-1].append(word)
    text = "\n".join(" ".join(word["text"] for word in sorted(line, key=lambda value: value["x0"]))
                     for line in lines)
    title = "Unofficial MIB 1, Early Voting, Election Day, and MIB2 Turnout"
    election = "Election: 2026 Gubernatorial General"
    if title not in text or election not in text or not all(
            label in text for label in ("Cards Cast", "Eligible Voters", "Percentage")):
        raise ValueError("Changed unofficial card units or election identity")
    pattern = r"^(.+?)\s+\((\d+) of (\d+)\)\s+([\d,]+)\s+([\d,]+)\s+(\d+\.\d+%)\s*$"
    rows = [dict(native_county_label=m[0].strip(), reported_source_units=int(m[1]),
        expected_source_units=int(m[2]), native_cards_cast=m[3],
        native_eligible_voters=m[4], native_percentage=m[5])
        for m in re.findall(pattern, text, re.M)]
    total = re.search(r"^Total\s+([\d,]+)\s+([\d,]+)\s+(\d+\.\d+%)\s*$", text, re.M)
    clock = re.search(r"Run Date:\s+(\d+/\d+/\d{4})\s+(\d+:\d+ [ap]m)", text)
    if len(rows) != 24 or total is None or clock is None:
        raise ValueError("Incomplete native card rows, printed total or source clock")
    rows.append(dict(native_county_label="Total", reported_source_units=None,
        expected_source_units=None, native_cards_cast=total[1],
        native_eligible_voters=total[2], native_percentage=total[3]))
    return dict(title=title, election=election, run_date=clock[1], run_time=clock[2], rows=rows)
