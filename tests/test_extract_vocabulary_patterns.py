import textwrap

from harvester.extract_vocabulary import extract_terms_and_definitions


def test_br_separated_bold_terms():
    html = textwrap.dedent(
        """
        <html><body>
          <div>
            <p>
              <b>Abactor</b> n. cattle thief<br>
              <b>Abaculus</b> n. a small tile<br>
              <b>Abacinate</b> v. to blind with red-hot metal<br>
            </p>
          </div>
        </body></html>
        """
    )
    pairs = extract_terms_and_definitions(html)
    terms = {td.term.lower() for td in pairs}
    assert "abactor" in terms
    assert "abaculus" in terms


def test_br_separated_anchor_bold_terms():
    html = textwrap.dedent(
        """
        <html><body>
          <div>
            <p>
              <a href="#a"><b>Abactor</b></a> — cattle thief<br>
              <a href="#b"><b>Abaculus</b></a> – a small tile<br>
              <a href="#c"><b>Abacinate</b></a> - to blind with red-hot metal<br>
            </p>
          </div>
        </body></html>
        """
    )
    pairs = extract_terms_and_definitions(html)
    terms = {td.term.lower() for td in pairs}
    assert {"abactor", "abaculus", "abacinate"}.issubset(terms)


def test_paragraph_pos_pattern():
    html = textwrap.dedent(
        """
        <html><body>
          <p>
            Abactor n. cattle thief\n
            Abaculus n. a small tile\n
            Abacinate v. to blind with red-hot metal
          </p>
        </body></html>
        """
    )
    pairs = extract_terms_and_definitions(html)
    terms = [td.term for td in pairs]
    assert terms[:3] == ["Abactor", "Abaculus", "Abacinate"]

