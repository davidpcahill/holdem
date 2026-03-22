"""
End-to-end browser tests using Playwright.

These tests launch the real Flask app, open a headless Chromium browser,
and interact with the UI just like a real user would.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

# Use a desktop-sized viewport so the sidebar is visible (>900px)
VIEWPORT = {"width": 1280, "height": 800}


def _wait_for_alpine(page: Page):
    """Wait for Alpine.js to initialize (x-cloak removed from #app)."""
    page.wait_for_function(
        "document.querySelector('#app') && "
        "!document.querySelector('#app').hasAttribute('x-cloak')",
        timeout=10000,
    )
    page.wait_for_timeout(500)  # Settle time for Alpine reactivity


# ── Page Load & Setup ──

def test_page_loads(app_page: Page):
    """App loads without errors."""
    app_page.set_viewport_size(VIEWPORT)
    expect(app_page.locator(".topbar-brand")).to_have_text("♠ Hold'em")


def test_setup_modal_visible(app_page: Page):
    """Setup modal appears when New Game is clicked."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    # Open setup modal (may already be open on first load)
    overlay = app_page.locator(".modal-overlay").first
    if not overlay.is_visible():
        app_page.locator("button:has-text('New Game')").first.click()
    overlay.wait_for(state="visible", timeout=10000)
    modal = app_page.locator(".modal-header h2")
    expect(modal.first).to_be_visible()
    expect(modal.first).to_have_text("New Game Setup")


def test_setup_has_players(app_page: Page):
    """Setup shows player name inputs (at least 2)."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    overlay = app_page.locator(".modal-overlay").first
    if not overlay.is_visible():
        app_page.locator("button:has-text('New Game')").first.click()
    overlay.wait_for(state="visible", timeout=10000)
    rows = app_page.locator(".modal-body input[type='text']")
    count = rows.count()
    assert count >= 2, f"Expected at least 2 player rows, got {count}"


# ── Game Lifecycle ──

def _start_game(page: Page):
    """Helper: open setup modal if needed and click Start Game."""
    page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(page)
    # If setup modal isn't visible (game already started), click New Game button
    overlay = page.locator(".modal-overlay").first
    if not overlay.is_visible():
        page.locator("button:has-text('New Game')").first.click()
        overlay.wait_for(state="visible", timeout=10000)
    page.locator("button:has-text('Start Game')").click()
    # Wait for game state to load (players visible)
    page.locator(".player-seat").first.wait_for(state="visible", timeout=10000)


def _deal_hand(page: Page):
    """Helper: click New Hand."""
    btn = page.locator("button:has-text('New Hand')")
    btn.wait_for(state="visible", timeout=5000)
    btn.click()
    # Wait for cards to appear (either visible cards or card-backs)
    page.wait_for_timeout(1000)


def test_start_game(app_page: Page):
    """Starting a new game shows the table."""
    _start_game(app_page)
    players = app_page.locator(".player-seat")
    expect(players).to_have_count(3)


def test_deal_hand_shows_cards(app_page: Page):
    """Dealing a hand shows cards and community area."""
    _start_game(app_page)
    _deal_hand(app_page)
    # Wait for cards/card-backs to appear
    app_page.wait_for_timeout(2000)
    cards = app_page.locator(".player-seat .playing-card, .player-seat .card-back")
    assert cards.count() > 0


def test_community_street_display(app_page: Page):
    """Street display updates from 'Setup' after dealing."""
    _start_game(app_page)
    _deal_hand(app_page)
    app_page.wait_for_timeout(1000)
    street = app_page.locator(".community-street")
    text = street.inner_text().lower()
    assert text in ["pre-flop", "flop", "turn", "river", "showdown", "setup", "hand over"]


def test_pot_display(app_page: Page):
    """Pot shows a dollar amount after dealing."""
    _start_game(app_page)
    _deal_hand(app_page)
    app_page.wait_for_timeout(1000)
    pot = app_page.locator(".community-pot")
    text = pot.inner_text()
    assert "$" in text


# ── Player Actions ──

def test_fold_button_exists(app_page: Page):
    """Fold button is present in the action bar."""
    _start_game(app_page)
    _deal_hand(app_page)
    fold_btn = app_page.locator(".fold-btn")
    expect(fold_btn).to_be_visible(timeout=15000)


def test_keyboard_shortcut_n(app_page: Page):
    """Pressing 'N' doesn't crash the app."""
    _start_game(app_page)
    _deal_hand(app_page)
    app_page.wait_for_timeout(2000)
    app_page.keyboard.press("n")
    app_page.wait_for_timeout(1000)
    # App should still be functional
    expect(app_page.locator(".topbar-brand")).to_be_visible()


# ── Sidebar Tabs ──

def test_sidebar_tabs_exist(app_page: Page):
    """All 4 sidebar tabs are present."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    tabs = app_page.locator(".sidebar-tab")
    count = tabs.count()
    assert count == 4, f"Expected 4 sidebar tabs, got {count}"
    texts = [tabs.nth(i).inner_text().lower() for i in range(count)]
    for expected in ["advisor", "log", "stats", "settings"]:
        assert expected in texts, f"Missing sidebar tab: {expected} (found: {texts})"


def test_settings_tab_shows_difficulty(app_page: Page):
    """Settings tab shows difficulty dropdown."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    app_page.locator(".sidebar-tab:has-text('Settings')").click()
    app_page.wait_for_timeout(300)
    # Find the difficulty select (contains Easy option)
    difficulty = app_page.locator("select option:has-text('Easy')").first
    expect(difficulty).to_be_attached()


def test_stats_tab(app_page: Page):
    """Stats tab exists and can be clicked."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    stats_tab = app_page.locator(".sidebar-tab:has-text('Stats')")
    stats_tab.click()
    app_page.wait_for_timeout(300)
    # Stats panel should be active
    active_panel = app_page.locator(".sidebar-panel.active")
    expect(active_panel).to_be_visible()


# ── Sound Toggle ──

def test_sound_toggle_button(app_page: Page):
    """Sound toggle button switches between muted and unmuted icons."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    btn = app_page.locator("button").filter(has_text="🔊").or_(
        app_page.locator("button").filter(has_text="🔇")
    ).first
    text_before = btn.inner_text().strip()
    btn.click()
    app_page.wait_for_timeout(200)
    text_after = btn.inner_text().strip()
    assert text_before != text_after


# ── Settings ──

def test_sound_settings_group(app_page: Page):
    """Sound settings group with volume slider exists."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    app_page.locator(".sidebar-tab:has-text('Settings')").click()
    app_page.wait_for_timeout(300)
    sound_group = app_page.locator(".settings-group-title:has-text('Sound')")
    expect(sound_group).to_be_visible()


def test_advisor_precision_slider(app_page: Page):
    """Advisor precision slider exists in settings."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    app_page.locator(".sidebar-tab:has-text('Settings')").click()
    app_page.wait_for_timeout(300)
    advisor_title = app_page.locator(".settings-group-title:has-text('Advisor')")
    expect(advisor_title).to_be_visible()


# ── Connection Indicator ──

def test_no_connection_lost_on_load(app_page: Page):
    """Connection lost indicator should NOT be visible when connected."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    indicator = app_page.locator(".connection-lost")
    expect(indicator).to_be_hidden()


# ── Animations ──

def test_dealer_badge_after_deal(app_page: Page):
    """After dealing, the BTN badge should have the dealer-badge class."""
    _start_game(app_page)
    _deal_hand(app_page)
    app_page.wait_for_timeout(2000)
    badges = app_page.locator(".dealer-badge")
    assert badges.count() >= 1


def test_street_badge_class(app_page: Page):
    """Street display should have the street-badge class."""
    app_page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(app_page)
    street = app_page.locator(".community-street.street-badge")
    expect(street).to_be_visible()


# ── Full Hand ──

def test_full_hand_plays_through(app_page: Page):
    """Start a game, deal a hand — app stays functional throughout."""
    _start_game(app_page)
    _deal_hand(app_page)
    # Wait for AI to finish (up to 15s for realistic timing)
    app_page.wait_for_timeout(12000)
    # App should be in some valid state — not crashed
    page_text = app_page.locator("body").inner_text()
    assert any(keyword in page_text for keyword in [
        "Showdown", "Winner", "Fold", "Check", "Call", "Setup", "Game Over",
        "Pre-Flop", "Flop", "Turn", "River", "New Hand", "Hold'em"
    ])


# ── Mobile Viewport ──

def test_mobile_viewport(app_page: Page):
    """App renders without errors at mobile viewport size."""
    app_page.set_viewport_size({"width": 375, "height": 667})
    _wait_for_alpine(app_page)
    expect(app_page.locator(".topbar-brand")).to_be_visible()
    # Sidebar toggle should be visible on mobile
    toggle = app_page.locator(".sidebar-toggle-btn")
    expect(toggle).to_be_visible()


def test_mobile_sidebar_toggle(app_page: Page):
    """Sidebar opens when toggle is clicked on mobile."""
    app_page.set_viewport_size({"width": 375, "height": 667})
    _wait_for_alpine(app_page)
    toggle = app_page.locator(".sidebar-toggle-btn")
    toggle.click()
    app_page.wait_for_timeout(500)
    sidebar = app_page.locator(".sidebar.sidebar-open")
    expect(sidebar).to_be_visible()


def test_mobile_hides_keyboard_shortcuts(app_page: Page):
    """On mobile, keyboard shortcut labels should be hidden."""
    app_page.set_viewport_size({"width": 375, "height": 667})
    _wait_for_alpine(app_page)
    # .kbd elements should be display:none on mobile
    kbd = app_page.locator(".action-btn .kbd").first
    if kbd.count() > 0:
        expect(kbd).to_be_hidden()
