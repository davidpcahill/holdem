"""
End-to-end browser tests for the 10-hand scripted tutorial.

Uses Playwright to walk through the full tutorial flow:
start → intro → deal → guided actions → outro → next hand → completion.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

VIEWPORT = {"width": 1280, "height": 800}

# Selectors for the three tutorial modals (distinguished by parent overlay's x-show)
INTRO_OVERLAY = '[x-show="tutorial.showIntro"]'
OUTRO_OVERLAY = '[x-show="tutorial.showOutro"]'
COMPLETE_OVERLAY = '[x-show="tutorial.showComplete"]'


# ── Helpers ──────────────────────────────────────────────────────────

def _wait_for_alpine(page: Page):
    """Wait for Alpine.js to initialize (x-cloak removed from #app)."""
    page.wait_for_function(
        "document.querySelector('#app') && "
        "!document.querySelector('#app').hasAttribute('x-cloak')",
        timeout=10000,
    )
    page.wait_for_timeout(500)


def _start_tutorial(page: Page):
    """Click 'Learn Poker' and wait for the intro modal."""
    page.set_viewport_size(VIEWPORT)
    _wait_for_alpine(page)
    # Reset any stale server state from previous tests
    page.evaluate("fetch('/api/tutorial/skip', {method: 'POST'})")
    page.wait_for_timeout(200)
    # Open setup modal if not already visible (button is inside setup modal)
    setup_overlay = page.locator(".modal-overlay").first
    if not setup_overlay.is_visible():
        page.locator("button:has-text('New Game')").first.click()
        setup_overlay.wait_for(state="visible", timeout=5000)
    btn = page.locator("button:has-text('Learn Poker')")
    btn.wait_for(state="visible", timeout=5000)
    btn.click()
    # Wait for intro overlay to become visible
    page.locator(INTRO_OVERLAY).wait_for(state="visible", timeout=10000)


def _click_deal_hand(page: Page):
    """Click 'Deal Hand' in the intro modal."""
    btn = page.locator(f"{INTRO_OVERLAY} button.btn-gold:has-text('Deal Hand')")
    btn.wait_for(state="visible", timeout=5000)
    btn.click()
    # Wait for game to be in playing state
    page.wait_for_timeout(1000)


def _click_guided_action(page: Page, timeout: int = 15000):
    """Find the highlighted guided-action button and click it."""
    guided = page.locator("button.guided-action:not([disabled])")
    guided.first.wait_for(state="visible", timeout=timeout)
    guided.first.click()
    # Wait for server to process action + bot turns (500ms sleep per bot turn)
    page.wait_for_timeout(3000)


def _is_outro_or_complete_visible(page: Page) -> bool:
    """Check if the outro or completion modal is visible via Alpine state."""
    return page.evaluate(
        "(() => {"
        "  const app = document.querySelector('#app')?.__x?.$data"
        "    || document.querySelector('#app')?._x_dataStack?.[0];"
        "  if (!app) return false;"
        "  return !!(app.tutorial?.showOutro || app.tutorial?.showComplete);"
        "})()"
    )


def _wait_for_outro_or_complete(page: Page, timeout: int = 20000):
    """Wait for the outro or completion modal to appear via Alpine state."""
    page.wait_for_function(
        "() => {"
        "  const app = document.querySelector('#app')?.__x?.$data"
        "    || document.querySelector('#app')?._x_dataStack?.[0];"
        "  if (!app) return false;"
        "  return !!(app.tutorial?.showOutro || app.tutorial?.showComplete);"
        "}",
        timeout=timeout,
    )


def _click_next_hand(page: Page):
    """Click 'Next Hand' in the outro modal."""
    btn = page.locator(f"{OUTRO_OVERLAY} button.btn-gold")
    btn.wait_for(state="visible", timeout=5000)
    btn.click()
    page.wait_for_timeout(500)


def _play_one_hand(page: Page, hand_num: int):
    """Play through one tutorial hand: deal → guided actions → outro → next."""
    # 1. Wait for intro overlay
    page.locator(INTRO_OVERLAY).wait_for(state="visible", timeout=10000)

    # 2. Click Deal Hand
    _click_deal_hand(page)

    # 3. Execute guided actions until outro or completion
    max_actions = 8  # safety limit (hand 10 has 6 guided actions)
    for _ in range(max_actions):
        if _is_outro_or_complete_visible(page):
            break

        # Check if a guided action is available
        guided = page.locator("button.guided-action:not([disabled])")
        if guided.count() > 0 and guided.first.is_visible():
            guided.first.click()
            page.wait_for_timeout(3000)  # Wait for bot turns
        else:
            page.wait_for_timeout(1000)

    # 4. Wait for outro or completion
    _wait_for_outro_or_complete(page, timeout=20000)

    # 5. Click Next Hand / See Results in the outro
    outro_btn = page.locator(f"{OUTRO_OVERLAY} button.btn-gold")
    if outro_btn.is_visible():
        outro_btn.click()
        page.wait_for_timeout(500)


# ── Tests ────────────────────────────────────────────────────────────

def test_tutorial_start_shows_intro(app_page: Page):
    """Clicking 'Learn Poker' shows the intro modal for Hand 1."""
    _start_tutorial(app_page)
    intro = app_page.locator(f"{INTRO_OVERLAY} .tutorial-modal")
    expect(intro).to_be_visible()
    title = intro.locator("h2")
    expect(title).to_contain_text("Welcome to Poker")


def test_tutorial_skip_returns_to_setup(app_page: Page):
    """Clicking 'Skip Tutorial' exits and shows the setup modal."""
    _start_tutorial(app_page)
    app_page.locator(f"{INTRO_OVERLAY} button:has-text('Skip Tutorial')").click()
    app_page.wait_for_timeout(500)
    setup = app_page.locator(".modal-header h2:has-text('New Game Setup')")
    expect(setup).to_be_visible(timeout=5000)


def test_tutorial_progress_bar_visible(app_page: Page):
    """After dealing, the tutorial progress bar shows Hand 1 of 10."""
    _start_tutorial(app_page)
    _click_deal_hand(app_page)
    progress = app_page.locator(".tutorial-progress")
    expect(progress).to_be_visible(timeout=5000)
    text = progress.inner_text()
    assert "1" in text and "10" in text, f"Expected 'Hand 1 of 10' in: {text}"


def test_guided_action_disables_others(app_page: Page):
    """Non-guided action buttons are disabled during tutorial."""
    _start_tutorial(app_page)
    _click_deal_hand(app_page)
    # Hand 1 guided action is "raise" — fold and check/call should be disabled
    app_page.locator("button.guided-action").first.wait_for(
        state="visible", timeout=10000
    )
    fold_btn = app_page.locator(".fold-btn")
    expect(fold_btn).to_be_disabled()


def test_slider_locked_during_tutorial(app_page: Page):
    """Bet slider is disabled and preset buttons are hidden during tutorial."""
    _start_tutorial(app_page)
    _click_deal_hand(app_page)
    app_page.locator("button.guided-action").first.wait_for(
        state="visible", timeout=10000
    )
    slider = app_page.locator(".bet-slider-row input[type='range']")
    expect(slider).to_be_disabled()
    presets = app_page.locator(".bet-presets")
    expect(presets).to_be_hidden()


def test_new_hand_blocked_during_tutorial(app_page: Page):
    """New Hand toolbar button is disabled during active tutorial."""
    _start_tutorial(app_page)
    _click_deal_hand(app_page)
    app_page.wait_for_timeout(500)
    new_hand_btn = app_page.locator("button:has-text('New Hand')").first
    expect(new_hand_btn).to_be_disabled()


def test_tutorial_hand1_completes(app_page: Page):
    """Hand 1: raise with Aces → bot folds → outro about Aces appears."""
    _start_tutorial(app_page)
    _click_deal_hand(app_page)
    _click_guided_action(app_page)
    _wait_for_outro_or_complete(app_page)

    outro = app_page.locator(f"{OUTRO_OVERLAY} .tutorial-modal")
    expect(outro).to_be_visible()
    text = outro.inner_text()
    assert "Aces" in text, f"Expected 'Aces' in outro: {text}"


def test_full_tutorial_playthrough(app_page: Page):
    """Play all 10 tutorial hands to completion — the key regression test."""
    _start_tutorial(app_page)

    for hand_num in range(1, 11):
        _play_one_hand(app_page, hand_num)

    # After hand 10: completion modal should show
    complete = app_page.locator(f"{COMPLETE_OVERLAY} .tutorial-modal")
    complete.wait_for(state="visible", timeout=15000)
    text = complete.inner_text()
    assert "Tutorial Complete" in text, f"Expected 'Tutorial Complete' in: {text}"
