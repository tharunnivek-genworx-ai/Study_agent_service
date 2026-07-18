"""Unit tests for rule-based content distillation (§7)."""

from __future__ import annotations

from src.api.utils.external_research_utils.content_distillation import (
    clean_extracted_text,
    distill_extracted_pages,
)

# Trace-shaped fixtures (abbreviated from EBSCO / Codecademy / React legacy logs).

_EBSCO_BIB_FIXTURE = """\
RESEARCH STARTER
Wave-particle Duality
Wave-particle duality is a fundamental concept in quantum mechanics that describes how every particle or quantum entity, such as electrons and photons, exhibits both wave and particle characteristics.
Key experiments, including Thomas Young's double-slit experiment, illustrated that light and matter can create interference patterns.
WAVELENGTH: the spatial repetition of a waveform; the distance covered by one complete wave oscillation
Bibliography
Beiser, Arthur. Concepts of Modern Physics. McGraw-Hill, 1987.
Burns, Marshall L. Modern Physics for Science and Engineering. Harcourt Brace Jovanovich, 1988.
Chu, Jennifer. "Famous Double-Slit Experiment Holds Up When Stripped to Its Quantum Essentials." MIT News, 28 July 2025.
Halliday, David, and Robert Resnick. Fundamentals of Physics. 3rd rev. ed., John Wiley & Sons.
More Like ThisRelated Articles
Related Articles (5)
- Brush Up for NEET/JEE Class XII.Published In: Physics For You, 2025
"""

_CODECADEMY_MARKETING_FIXTURE = """\
Learn React: Hooks
Leverage hooks, a powerful feature of function components, to use states without creating classes.
- Skill level Beginner
- Time to complete Average based on combined completion rates — individual pacing in lessons, projects, and quizzes may vary5 hours
- Projects 1
- Prerequisites None
About this course
Continue your React learning journey with Learn React: Hooks. Level-up your React applications with hooks, a powerful feature of function components.
Skills you'll gain
- Write function components
- Create state hooks
- Implement effect hooks
Syllabus
- Hooks- Learn how to use Hooks in React, a powerful feature of function components.
- Certificate of completion available with Plus or ProEarn a certificate of completion and showcase your accomplishment on your resume or LinkedIn.
Earn a certificate of completion
Show your network you've done the work by earning a certificate of completion for each course or path you finish.
 Learn React: Hooks course ratings and reviews
- 5 stars
- 4 stars
- 3 stars
- 2 stars
- 1 star
Our learners work at
Join over 50 million learners and start Learn React: Hooks today!
Looking for something else?
Related courses and paths
Browse more topics
- Web development5,927,368 learners enrolled
- JavaScript3,304,713 learners enrolled
Unlock additional features with a paid plan
"""

_REACT_BANNER_FIXTURE = """\
These docs are old and won't be updated. Go to react.dev for the new React docs.
These new documentation pages teach React with Hooks:
Hooks are a new addition in React 16.8. They let you use state and other React features without writing a class.
import React, { useState } from 'react';
function Example() {
  const [count, setCount] = useState(0);
  return (
    <div>
      <p>You clicked {count} times</p>
      <button onClick={() => setCount(count + 1)}>Click me</button>
    </div>
  );
}
"""


def test_bibliography_section_truncated_keeps_article_body():
    cleaned = clean_extracted_text(_EBSCO_BIB_FIXTURE)
    assert "Wave-particle duality is a fundamental concept" in cleaned
    assert "WAVELENGTH: the spatial repetition" in cleaned
    assert "Bibliography" not in cleaned
    assert "Beiser, Arthur" not in cleaned
    assert "More Like This" not in cleaned
    assert "Related Articles" not in cleaned
    # Bibliography mass was a large fraction of the raw page
    assert len(cleaned) < 0.6 * len(_EBSCO_BIB_FIXTURE)


def test_codecademy_marketing_and_enrollment_chrome_cut():
    cleaned = clean_extracted_text(_CODECADEMY_MARKETING_FIXTURE)
    assert "About this course" in cleaned
    assert "Write function components" in cleaned
    assert "Skill level" not in cleaned
    assert "learners enrolled" not in cleaned
    assert "Certificate of completion" not in cleaned
    assert "Our learners work at" not in cleaned
    assert "Related courses and paths" not in cleaned
    assert "Looking for something else" not in cleaned
    assert "5 stars" not in cleaned
    assert len(cleaned) < 0.7 * len(_CODECADEMY_MARKETING_FIXTURE)


def test_react_legacy_docs_banner_stripped_keeps_hooks_body():
    cleaned = clean_extracted_text(_REACT_BANNER_FIXTURE)
    assert "These docs are old" not in cleaned
    assert "Go to react.dev" not in cleaned
    assert "Hooks are a new addition in React 16.8" in cleaned
    assert "useState" in cleaned
    assert "const [count, setCount]" in cleaned


def test_mid_body_references_not_truncated_in_first_half():
    """Ambiguous 'References' heading early in the doc must not wipe the article."""
    # Build a page where a heading-like "References" appears in the first half
    # (e.g. a section about DOM references), with real content after it.
    early = (
        "React Hooks Overview\n"
        "Hooks let you use state in function components.\n"
        "References\n"
        "Commonly used for DOM references and mutable variables.\n"
        "useRef returns a mutable ref object whose .current property is initialized.\n"
        "You can keep reading about cleanup and effects below.\n"
    )
    # Pad so "References" lands in the first half by character position
    padding = "More teaching content about effects and cleanup. " * 40
    text = early + padding
    refs_pos = text.index("\nReferences\n")
    assert refs_pos < len(text) / 2

    cleaned = clean_extracted_text(text)
    assert "Commonly used for DOM references" in cleaned
    assert "useRef returns a mutable ref object" in cleaned
    assert "More teaching content about effects" in cleaned


def test_references_heading_truncated_in_latter_half():
    body = (
        "Article body explains the experiment and results in detail.\n"
        "Young's double-slit setup produced interference fringes.\n"
    ) * 20
    text = (
        body + "References\nSmith, A. Quantum Primer. 2020.\nJones, B. Optics. 2019.\n"
    )
    refs_pos = text.index("\nReferences\n")
    assert refs_pos >= len(text) / 2

    cleaned = clean_extracted_text(text)
    assert "Young's double-slit setup" in cleaned
    assert "References" not in cleaned
    assert "Smith, A." not in cleaned


def test_wiki_pipe_table_noise_lines_dropped():
    text = (
        "Wave–particle duality\n"
        "Matter exhibits both wave and particle properties.\n"
        "| Part of a series of articles about | \n"
        "| Quantum mechanics | \n"
        "|---|\n"
        "De Broglie proposed λ = h/p in 1924.\n"
    )
    cleaned = clean_extracted_text(text)
    assert "Matter exhibits both wave and particle properties" in cleaned
    assert "De Broglie proposed" in cleaned
    assert "Part of a series" not in cleaned
    assert "| Quantum mechanics |" not in cleaned


def test_wiki_comparison_table_not_stripped():
    """Multi-column teaching tables must not be removed as series chrome."""
    text = (
        "Particle properties compared:\n"
        "| Property | Electron | Photon |\n"
        "| mass | 9.1e-31 kg | 0 |\n"
        "| charge | -e | 0 |\n"
        "Both exhibit interference in the double-slit experiment.\n"
    )
    cleaned = clean_extracted_text(text)
    assert "| Property | Electron | Photon |" in cleaned
    assert "| mass | 9.1e-31 kg | 0 |" in cleaned
    assert "Both exhibit interference" in cleaned


def test_wiki_two_pipe_series_chrome_dropped():
    """Wikipedia 'Part of a series' rows often have only two pipes."""
    text = (
        "| Part of a series of articles about | \n"
        "| Quantum mechanics | \n"
        "|---|\n"
        "Wave–particle duality is the concept in quantum mechanics that "
        "fundamental entities exhibit particle and wave properties.\n"
        "De Broglie proposed λ = h/p in 1924.\n"
    )
    cleaned = clean_extracted_text(text)
    assert "Part of a series" not in cleaned
    assert "Quantum mechanics |" not in cleaned
    assert "|---|" not in cleaned
    assert "Wave–particle duality is the concept" in cleaned
    assert "De Broglie proposed" in cleaned


def test_wiki_headingless_see_also_and_citation_run_truncated():
    """When extractors drop References/See also headings, cut citation dumps."""
    body = (
        "Wave–particle duality is the concept in quantum mechanics that "
        "fundamental entities of the universe exhibit particle and wave properties. "
        "The electron double slit experiment is a textbook demonstration. "
        "Davisson–Germer measured electron diffraction from a nickel crystal. "
    ) * 8
    see_also = (
        "- Basic concepts of quantum mechanics – Non-mathematical introduction\n"
        "- Complementarity (physics) – Quantum physics concept\n"
        "- Uncertainty principle\n"
        "- Matter wave\n"
    )
    citations = (
        "- Messiah, Albert (1966). Quantum Mechanics. North Holland. ISBN 0-486-40924-4.\n"
        '- Planck, Max (1901). "Ueber das Gesetz". Annalen der Physik. Bibcode:1901AnP...309..553P.\n'
        '- Einstein, Albert (1905). "Heuristischen Gesichtspunkt". Annalen der Physik. doi:10.1002/andp.19053220607.\n'
        '- R. Nave. "Wave–Particle Duality". HyperPhysics. Retrieved December 12, 2005.\n'
        '- "Wave–particle duality". PhysicsQuest. American Physical Society. Retrieved August 31, 2023.\n'
    )
    text = body + "\n" + see_also + citations
    assert text.index("- Messiah, Albert") >= len(text) / 2

    cleaned = clean_extracted_text(text)
    assert "Wave–particle duality is the concept" in cleaned
    assert "Davisson–Germer measured electron diffraction" in cleaned
    assert "Messiah, Albert" not in cleaned
    assert "ISBN" not in cleaned
    assert "Basic concepts of quantum mechanics" not in cleaned
    assert "Uncertainty principle" not in cleaned
    assert len(cleaned.split()) < len(text.split())


def test_teaching_bullets_before_trailing_citations_are_kept():
    """See-also walk-back must not eat ordinary teaching bullets."""
    body = (
        "Hooks let you use state without classes. "
        "Remember these rules when writing components. "
    ) * 30
    teaching = (
        "- useState manages local state\n"
        "- useEffect runs after paint\n"
        "- Call hooks only at the top level\n"
    )
    citations = (
        "- Doe, Jane (2020). React Patterns. ISBN 978-1-234567-89-0.\n"
        "- Smith, John (2021). Hooks Guide. doi:10.1000/hooks.2021.\n"
        "- Lee, A. (2019). FAQ. Retrieved January 1, 2020.\n"
    )
    text = body + "\n" + teaching + citations
    assert text.index("- Doe, Jane") >= len(text) / 2

    cleaned = clean_extracted_text(text)
    assert "useState manages local state" in cleaned
    assert "Call hooks only at the top level" in cleaned
    assert "Doe, Jane" not in cleaned
    assert "ISBN" not in cleaned


def test_mid_article_citation_run_does_not_truncate_following_body():
    """Citation-like bullets mid-page must not wipe later teaching content."""
    body_before = (
        "Introduces wave–particle duality and early experiments. " * 40
    ) + "\n"
    cites = (
        "- Messiah, Albert (1966). Quantum Mechanics. ISBN 0-486-40924-4.\n"
        "- Planck, Max (1901). Annalen. Bibcode:1901AnP...309..553P.\n"
        "- Einstein, Albert (1905). Annalen. doi:10.1002/andp.19053220607.\n"
    )
    body_after = (
        "\nAfter the historical notes, here is the double-slit setup in detail.\n"
        "Electrons arrive one at a time yet still form an interference pattern.\n"
        "This is the core teaching point students must retain.\n"
    )
    text = body_before + cites + body_after
    assert text.index("- Messiah, Albert") >= len(text) / 2

    cleaned = clean_extracted_text(text)
    assert "core teaching point students must retain" in cleaned
    assert "interference pattern" in cleaned
    # Mid-list citations are kept when body follows (safer than silent loss)
    assert "Messiah, Albert" in cleaned


def test_mid_body_bullets_not_cut_without_citation_run():
    """Ordinary teaching bullets mid-article must not trigger wiki truncation."""
    text = (
        "Hooks overview.\n"
        "- useState manages local state\n"
        "- useEffect runs after render\n"
        "- useRef holds mutable values\n"
        "Rules of Hooks require top-level calls only.\n"
    ) * 5
    cleaned = clean_extracted_text(text)
    assert "useState manages local state" in cleaned
    assert "Rules of Hooks require top-level calls only" in cleaned


def test_see_also_classifier_rejects_teaching_bullets():
    from src.api.utils.external_research_utils.content_distillation import (
        _is_see_also_line,
    )

    assert _is_see_also_line(
        "- Basic concepts of quantum mechanics – Non-mathematical introduction"
    )
    assert _is_see_also_line("- Uncertainty principle")
    assert not _is_see_also_line("- useState manages local state")
    assert not _is_see_also_line("- Write function components")
    assert not _is_see_also_line("- Eliminate the need for class components")
    assert not _is_see_also_line("- Electrons diffract through slits")
    assert not _is_see_also_line("- Momentum is p = h/λ")
    assert not _is_see_also_line("- Key property: wave interference")


def test_distill_extracted_pages_maps_url_and_cleaned_text():
    pages = distill_extracted_pages(
        [
            {
                "url": "https://example.com/ebsco",
                "raw_text": _EBSCO_BIB_FIXTURE,
            }
        ]
    )
    assert len(pages) == 1
    assert pages[0]["url"] == "https://example.com/ebsco"
    assert "Bibliography" not in pages[0]["cleaned_text"]
    assert "Wave-particle duality" in pages[0]["cleaned_text"]
