# tests/e2e/test_player_add.py
import os
import re
# import time
import pytest
from decimal import Decimal
from playwright.sync_api import expect

# Django ORM (pytest-django loads settings for us)
from django.utils import timezone
from GRPR.models import Players, Log

BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
USER = os.getenv("E2E_LOGIN_USER", "")
PASS = os.getenv("E2E_LOGIN_PASS", "")

def _login(page):
    assert USER, "Set E2E_LOGIN_USER"
    assert PASS, "Set E2E_LOGIN_PASS"

    # Hit your Django auth login page
    page.goto(f"{BASE}/login/")
    page.get_by_label("Username").fill(USER)
    page.get_by_label("Password").fill(PASS)
    page.get_by_role("button", name="Login").click()

    # Wait for post-login network to settle
    page.wait_for_load_state("networkidle")

    # Go to the home dashboard that shows the buttons
    page.goto(f"{BASE}/GRPR/home/", wait_until="domcontentloaded")

    # ✅ Playwright expects a string or regex here (not a lambda)
    expect(page).to_have_url(re.compile(r"/GRPR/home/?$"))


@pytest.fixture
def cleanup_byrne():
    """
    Remove David Byrne test data before & after a test.
    Safe to call even if no rows exist.
    """
    Players.objects.filter(FirstName="David", LastName="Byrne").delete()
    yield
    Players.objects.filter(FirstName="David", LastName="Byrne").delete()


def _ensure_byrne_exists(crew_id=1):
    """
    Seed a David Byrne in the DB using normalized values your view expects.
    Mirrors the view’s normalization (index decimals, mobile E.164-ish).
    """
    # Normalize what your view would save:
    # Index as Decimal("11.1")
    # Mobile raw "212-744-9087" -> "12127449087" (your helper)
    # GHIN 13 digits
    mobile_norm = "12127449087"
    player, _ = Players.objects.get_or_create(
        CrewID=crew_id,
        FirstName="David",
        LastName="Byrne",
        defaults={
            "Email": "dbyrne@th.com",
            "Mobile": mobile_norm,
            "SplitPartner": None,
            "Member": 0,
            "GHIN": "0123456789321",
            "Index": Decimal("11.1"),
            "user_id": None,
        },
    )
    return player


@pytest.mark.playwright
def test_login_shows_players_button(page):
    _login(page)

    # Find the "Players" control on the home page
    players = page.get_by_role("button", name="Players")
    if not players.count():
        players = page.get_by_role("link", name="Players")
    if not players.count():
        players = page.locator("a.btn", has_text="Players")

    expect(players).to_be_visible()

@pytest.mark.playwright
def test_login_then_open_players(page):
    _login(page)

    # Click Players from home
    players = page.get_by_role("button", name="Players")
    if not players.count():
        players = page.get_by_role("link", name="Players")
    if not players.count():
        players = page.locator("a.btn", has_text="Players")

    expect(players).to_be_visible()
    players.click()

    # Land on the players page
    page.wait_for_load_state("networkidle")
    page.wait_for_url("**/GRPR/players/**")


@pytest.mark.playwright
def test_open_add_player(page):
    _login(page)

    page.goto(f"{BASE}/GRPR/players/", wait_until="domcontentloaded")

    add_link = page.get_by_role("link", name="Add Player")
    expect(add_link).to_be_visible()
    add_link.click()

    # Either assert by the actual URL…
    page.wait_for_url("**/GRPR/players/add/**")

    # …and/or assert by a page-specific heading rendered on player_add.html
    # (Uncomment if your template has this exact text.)
    # expect(page.get_by_role("heading", name="Add a New Player")).to_be_visible()


@pytest.mark.playwright
def test_fill_add_player_form(page):
    # 1) Login
    _login(page)

    # 2) Open Players page and then Add Player form
    page.goto(f"{BASE}/GRPR/players/", wait_until="domcontentloaded")
    page.get_by_role("link", name="Add Player").click()
    page.wait_for_url("**/players/add/**")  # /GRPR/players/add/

    # 3) Fill fields (no submit)
    page.locator('input[name="first_name"]').fill("David")
    page.locator('input[name="last_name"]').fill("Byrne")
    page.locator('input[name="index"]').fill("11.1")
    page.locator('input[name="email"]').fill("dbyrne@th.com")
    page.locator('input[name="mobile"]').fill("2127449087")
    page.locator('input[name="ghin"]').fill("0123456789321")

    # 4) Assert the values are present (and we didn't submit)
    expect(page.locator('input[name="first_name"]')).to_have_value("David")
    expect(page.locator('input[name="last_name"]')).to_have_value("Byrne")
    expect(page.locator('input[name="index"]')).to_have_value("11.1")
    expect(page.locator('input[name="email"]')).to_have_value("dbyrne@th.com")
    expect(page.locator('input[name="mobile"]')).to_have_value("2127449087")
    expect(page.locator('input[name="ghin"]')).to_have_value("0123456789321")

    # Extra sanity: heading is present on the form
    expect(page.get_by_role("heading", name="Add a New Player")).to_be_visible()

    # And ensure we're still on the add form URL (no submit happened)
    expect(page).to_have_url(re.compile(r"/GRPR/players/add/?$"))


@pytest.mark.playwright
def test_submit_add_player_form_fixed_values(page):
    _login(page)

    # Go to Players list then into Add Player
    page.goto(f"{BASE}/GRPR/players/", wait_until="domcontentloaded")
    page.get_by_role("link", name="Add Player").click()
    page.wait_for_url("**/GRPR/players/add/**")

    # --- Fill the form with the fixed values you provided ---
    first = "David"
    last  = "Byrne"
    idx   = "11.1"
    email = "dbyrne@th.com"
    mobile = "212-744-9087"       # raw; view normalizes to 11-digit or leaves raw if invalid
    ghin   = "0123456789321"

    page.locator('input[name="first_name"]').fill(first)
    page.locator('input[name="last_name"]').fill(last)
    page.locator('input[name="index"]').fill(idx)
    page.locator('input[name="email"]').fill(email)
    page.locator('input[name="mobile"]').fill(mobile)
    page.locator('input[name="ghin"]').fill(ghin)

    # Submit
    page.get_by_role("button", name="Add Player").click()
    page.wait_for_load_state("networkidle")

    # --- Success path (form is cleared, preview card shows saved values) ---
    first_val = page.locator('input[name="first_name"]').input_value()
    last_val  = page.locator('input[name="last_name"]').input_value()

    if first_val == "" and last_val == "":
        # We assume success; verify the preview card shows what was saved
        # Card has definition list rows; keep checks simple and robust.
        expect(page.locator(".card .card-title")).to_have_text(
            re.compile(r"Submitted|Player Added", re.I)
        )
        expect(page.locator(".card")).to_contain_text(first)
        expect(page.locator(".card")).to_contain_text(last)
        # Index as rendered (string); email appears verbatim
        expect(page.locator(".card")).to_contain_text(idx)
        expect(page.locator(".card")).to_contain_text(email)
        # Mobile may be normalized to 11 digits; accept either
        card_text = page.locator(".card").inner_text()
        assert ("212-744-9087" in card_text) or ("12127449087" in card_text), \
            f"Expected mobile raw or normalized in preview, got:\n{card_text}"
        # GHIN appears as entered
        expect(page.locator(".card")).to_contain_text(ghin)
        return

    # --- Failure path (errors shown; form retains values) ---
    # Capture any visible error content for debugging
    error_blocks = page.locator(".alert-danger, .invalid-feedback, .text-danger, ul.errorlist, .alert-warning")
    assert error_blocks.first.is_visible(), "Expected validation/constraint errors to be shown on failure."

    # Keep sticky values
    expect(page.locator('input[name="first_name"]')).to_have_value(first)
    expect(page.locator('input[name="last_name"]')).to_have_value(last)
    expect(page.locator('input[name="index"]')).to_have_value(idx)
    expect(page.locator('input[name="email"]')).to_have_value(email)
    expect(page.locator('input[name="mobile"]')).to_have_value(mobile)
    expect(page.locator('input[name="ghin"]')).to_have_value(ghin)

    # (Optional) print error texts to test output to help future debugging
    print("Form errors:\n", error_blocks.all_inner_texts())


@pytest.mark.playwright
def test_add_player_rejects_duplicate(page):
    _login(page)

    # Go to Add Player form
    page.goto(f"{BASE}/GRPR/players/", wait_until="domcontentloaded")
    page.get_by_role("link", name="Add Player").click()
    page.wait_for_url("**/GRPR/players/add/**")

    # Use the same fixed values
    first = "David"
    last  = "Byrne"
    idx   = "11.1"
    email = "dbyrne@th.com"
    mobile = "212-744-9087"
    ghin   = "0123456789321"

    def fill_and_submit():
        page.locator('input[name="first_name"]').fill(first)
        page.locator('input[name="last_name"]').fill(last)
        page.locator('input[name="index"]').fill(idx)
        page.locator('input[name="email"]').fill(email)
        page.locator('input[name="mobile"]').fill(mobile)
        page.locator('input[name="ghin"]').fill(ghin)
        page.get_by_role("button", name="Add Player").click()
        page.wait_for_load_state("networkidle")

    # First attempt: may succeed (if Byrne not present) or fail (already present).
    fill_and_submit()

    # Detect success (fields cleared + “Player Added Successfully” heading),
    # and if so, immediately try to add the same player again so we *force* a duplicate.
    success_heading = page.locator("h1", has_text=re.compile(r"Player Added Successfully", re.I))
    first_val = page.locator('input[name="first_name"]').input_value()
    last_val  = page.locator('input[name="last_name"]').input_value()
    if success_heading.first.is_visible() or (first_val == "" and last_val == ""):
        # Navigate back to the form if you’re not already on it
        page.goto(f"{BASE}/GRPR/players/", wait_until="domcontentloaded")
        page.get_by_role("link", name="Add Player").click()
        page.wait_for_url("**/GRPR/players/add/**")
        fill_and_submit()

    # Now we expect duplicate/validation errors and sticky values
    errors = page.locator(".alert-danger, .invalid-feedback, .text-danger, ul.errorlist, .alert-warning")
    assert errors.first.is_visible(), "Expected duplicate/validation errors when adding an existing player."

    expect(page.locator('input[name="first_name"]')).to_have_value(first)
    expect(page.locator('input[name="last_name"]')).to_have_value(last)
    expect(page.locator('input[name="index"]')).to_have_value(idx)
    expect(page.locator('input[name="email"]')).to_have_value(email)
    expect(page.locator('input[name="mobile"]')).to_have_value(mobile)
    expect(page.locator('input[name="ghin"]')).to_have_value(ghin)

    # Optional: print server-provided error text to the test output
    print("Duplicate form errors:\n", errors.all_inner_texts())
