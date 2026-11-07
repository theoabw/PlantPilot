from plantpilot import corpus

TOC = """Contents
1   INTRODUCTION TO PIPELINE FLOW.........................................8
1.1     General...........................................................................8
3.3.2   Investigating the existence of cavitation.........................50
3.4     Cavitation and hydrodynamic noise abatement..........................55
4   GAS AND STEAM FLOW...................................................66
"""


def test_parse_toc_ids_pages_and_end_pages():
    sections = corpus.parse_toc([TOC])
    assert [s.sid for s in sections] == ["1", "1.1", "3.3.2", "3.4", "4"]
    by_id = {s.sid: s for s in sections}
    assert by_id["1"].page == 8
    assert by_id["3.3.2"].end_page == 54
    assert by_id["3.4"].end_page == 65


def test_junk_lines_drop_headers_equations_and_rules():
    assert corpus.is_junk_line("50                                     Liquid flow")
    assert corpus.is_junk_line("Liquid flow 47")
    assert corpus.is_junk_line("==========================================")
    assert corpus.is_junk_line("a")
    assert not corpus.is_junk_line(
        "The value of exponent n in equation (33) can be as high as 7 in cases of erosion."
    )


def test_first_quote_skips_short_and_symbol_heavy_sentences():
    body = "v s = N 14 ⋅ k---------- where vs = sonic velocity. " \
           "Cavitation corrosion appears as pitting on the seat ring surface after throttling."
    quote = corpus.first_quote(body)
    assert quote.startswith("Cavitation corrosion")


def test_search_and_section_against_build_if_present():
    from pathlib import Path

    db = Path(__file__).resolve().parents[3] / "data" / "index.db"
    if not db.exists():
        return
    # Skip when the index exists but has no sections: pdftotext (poppler) was
    # not available when make corpus ran, so the DB is an empty shell.
    if corpus.count(db) == 0:
        return
    rows = corpus.search(db, "cavitation damage", 2)
    assert rows and rows[0]["page"] > 0 and rows[0]["anchor"].startswith("#page=")
    one = corpus.section(db, rows[0]["id"])
    assert one and one["title"]
