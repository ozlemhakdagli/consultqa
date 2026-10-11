import pytest

pytestmark = pytest.mark.e2e


def test_the_stub_server_serves_a_page_in_headless_chrome(page, base_url):
    response = page.goto(base_url + "/")
    assert response is not None and response.status == 200
    assert page.title()
