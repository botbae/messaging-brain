import pytest

from core.paths import UnsafeClientName, client_dir


def test_client_dir_stays_inside_clients():
    assert client_dir("acme").as_posix() == "clients/acme"


@pytest.mark.parametrize("bad", ["", "..", "../x", "/etc", "a/b", "a\\b", "a\nb", " "])
def test_client_dir_rejects_escapes(bad):
    with pytest.raises(UnsafeClientName):
        client_dir(bad)


def test_init_client_state_rejects_bad_name():
    from core.client_state import init_client_state

    assert "error" in init_client_state("../outside")
