import pytest

from core.output import slugify
from core.utils import clean_phrase, clean_sentence, is_safe_client_slug


def test_clean_phrase_keeps_first_sentence_without_period():
    assert clean_phrase("  Founders   struggle. Second part.") == "Founders struggle"


def test_clean_sentence_adds_period():
    assert clean_sentence("hello") == "hello."
    assert clean_sentence("") == ""


def test_slugify():
    assert slugify("AI UX Writing Operator!") == "ai-ux-writing-operator"
    assert slugify("") == "product"


@pytest.mark.parametrize("slug", ["acme", "test-unimind-clean", "qa_case_001", "A1"])
def test_safe_client_slugs(slug):
    assert is_safe_client_slug(slug)


@pytest.mark.parametrize("slug", ["", "/etc", "../x", "a/b", ".", "has space", "x" * 65])
def test_unsafe_client_slugs(slug):
    assert not is_safe_client_slug(slug)


def test_trailing_newline_is_not_a_safe_slug():
    assert not is_safe_client_slug("acme\n")


def test_unicode_letters_are_allowed():
    assert is_safe_client_slug("café")
