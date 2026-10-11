import pytest
from ui_helpers import run_js

pytestmark = pytest.mark.e2e

FAST_POLL_MS = 50  # the short job poll that the opt-in fixture serves; the default is 1000


def _served_job_poll_ms(page, base_url):
    """The JOB_POLL_MS that the page's own copy of /js/config.js exports."""
    return run_js(page, base_url, "return (await import('/js/config.js')).JOB_POLL_MS;")


def test_the_stub_server_serves_a_page_in_headless_chrome(page, base_url):
    response = page.goto(base_url + "/")
    assert response is not None and response.status == 200
    assert page.title()


def test_pages_keep_the_default_job_poll(page, base_url):
    assert _served_job_poll_ms(page, base_url) == 1000


@pytest.mark.usefixtures("fast_job_polling")
def test_the_opt_in_fixture_serves_a_short_job_poll(page, base_url):
    assert _served_job_poll_ms(page, base_url) == FAST_POLL_MS


def test_make_page_serves_a_short_job_poll_only_when_asked(make_page, base_url):
    assert _served_job_poll_ms(make_page(fast_jobs=True), base_url) == FAST_POLL_MS
    assert _served_job_poll_ms(make_page(), base_url) == 1000
