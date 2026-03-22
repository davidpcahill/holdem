"""
Scripted Tutorial System for Texas Hold'em.

Provides 10 progressive hands with predetermined cards, scripted bot actions,
guided player actions, and contextual tips that teach poker from scratch.
Culminates in a dramatic all-in showdown the player wins.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any


# ── 10 Scripted Tutorial Hands ─────────────────────────────────────────

TUTORIAL_HANDS: List[Dict[str, Any]] = [
    # ── Hand 1: Basics & Hand Strength ──────────────────────────────
    {
        "title": "Basics & Hand Strength",
        "intro": {
            "title": "Welcome to Poker! 🂡",
            "body": (
                "You're about to learn Texas Hold'em — the world's most popular poker game.\n\n"
                "**How it works:** You and the bot each get 2 private cards. "
                "5 shared cards are dealt on the table. Make the best 5-card hand to win!\n\n"
                "We'll start you with the **best possible hand** — pocket Aces. "
                "Watch the Advisor panel on the right for guidance."
            ),
        },
        "player_cards": ["Ah", "As"],
        "bot_cards": ["7d", "2c"],
        "community": ["Ks", "8d", "3c", "5h", "Jd"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            "preflop": [{"action": "fold", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "raise",
                "tip": (
                    "You have **pocket Aces** — the strongest starting hand! "
                    "The Advisor shows ~85% equity (win chance). Raise to build the pot."
                ),
            },
        ],
        "outro": {
            "title": "Nice — You Won with Aces!",
            "body": (
                "The bot folded to your raise. Premium hands like **AA, KK, QQ** "
                "should almost always be raised preflop to build the pot and thin the field.\n\n"
                "**Key concept:** The Advisor's *Equity* bar shows your win probability."
            ),
        },
    },

    # ── Hand 2: The Flop & Pairing Up ──────────────────────────────
    # dealer=0 (human): pre human first, postflop bot first
    {
        "title": "The Flop & Making a Hand",
        "intro": {
            "title": "Seeing the Flop",
            "body": (
                "After preflop betting, 3 community cards are dealt face-up — the **Flop**.\n\n"
                "Your hand = your 2 cards + the 5 community cards. "
                "The best 5-card combination wins.\n\n"
                "This time you have **Ace-King** — a premium starting hand. "
                "Let's see if you connect with the flop!"
            ),
        },
        "player_cards": ["As", "Ks"],
        "bot_cards": ["9h", "7c"],
        "community": ["Ad", "6h", "2c", "9d", "4s"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            # pre: human raises, bot calls
            "preflop": [{"action": "call", "amount": 0}],
            # flop: bot acts first — checks, then folds to human bet
            "flop": [{"action": "check", "amount": 0}, {"action": "fold", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "raise",
                "tip": (
                    "**Ace-King suited** is a top-5 starting hand. Raise it up! "
                    "Check the Advisor — it'll show your equity and recommended action."
                ),
            },
            {
                "street": "flop",
                "action": "bet",
                "tip": (
                    "You paired your Ace on the flop — **top pair, top kicker**! "
                    "The bot checked to you — showing weakness. "
                    "Bet to protect your hand and extract value."
                ),
            },
        ],
        "outro": {
            "title": "Top Pair Wins!",
            "body": (
                "Pairing one of your hole cards with a community card is the most common "
                "way to make a hand. **Top pair + top kicker** (like A-K hitting an Ace) "
                "is strong — bet it for value!\n\n"
                "**Key concept:** Look at the *Best Hand* section in the Advisor."
            ),
        },
    },

    # ── Hand 3: Position Power ─────────────────────────────────────
    # dealer=0 (human): pre human first, postflop bot first
    {
        "title": "Position Advantage",
        "intro": {
            "title": "Why Position Matters",
            "body": (
                "In poker, acting **last** is a huge advantage — you see what your "
                "opponent does before deciding.\n\n"
                "The **Button** (dealer) acts last on every street after the flop. "
                "This hand, you're on the Button with a decent hand. "
                "Notice the position modifier in the Advisor."
            ),
        },
        "player_cards": ["Kh", "Qs"],
        "bot_cards": ["Td", "8d"],
        "community": ["Kd", "5c", "2h", "6s", "3d"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            # pre: human raises, bot calls
            "preflop": [{"action": "call", "amount": 0}],
            # flop: bot acts first — checks, then folds to human's bet
            "flop": [{"action": "check", "amount": 0}, {"action": "fold", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "raise",
                "tip": (
                    "**K-Q** from the Button — a strong hand + great position! "
                    "The Advisor shows a positive position modifier. Raise!"
                ),
            },
            {
                "street": "flop",
                "action": "bet",
                "tip": (
                    "You flopped top pair (Kings). Your opponent checked — "
                    "they showed weakness. Acting last lets you control the pot size. Bet!"
                ),
            },
        ],
        "outro": {
            "title": "Position is Power!",
            "body": (
                "From the Button you saw your opponent check before deciding. "
                "Play **more hands** from late position (BTN, CO) and **fewer** from "
                "early position (UTG, SB).\n\n"
                "**Key concept:** The Advisor's position modifier boosts equity from late position."
            ),
        },
    },

    # ── Hand 4: Pot Odds & Flush Draw ──────────────────────────────
    # dealer=0 (human): pre human first, postflop bot first
    {
        "title": "Pot Odds & Drawing",
        "intro": {
            "title": "When to Chase a Draw",
            "body": (
                "Sometimes you don't have a made hand yet, but you have a **draw** — "
                "cards that can complete a strong hand.\n\n"
                "**Pot Odds** tell you if calling is profitable: compare the cost to "
                "the pot size. If your odds of hitting are better than the pot odds, call!\n\n"
                "This hand you'll have a **flush draw** (4 cards of one suit, needing 1 more)."
            ),
        },
        "player_cards": ["9s", "8s"],
        "bot_cards": ["Ah", "Qd"],
        "community": ["Ks", "4s", "2c", "7s", "Jd"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            # pre: human calls SB, bot raises from BB
            "preflop": [{"action": "raise", "amount": 30}],
            # flop: bot acts first — bets, then folds to human's reraise (won't happen)
            "flop": [{"action": "bet", "amount": 30}],
            # turn: bot acts first — checks, then folds to human's bet
            "turn": [{"action": "check", "amount": 0}, {"action": "fold", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "call",
                "tip": (
                    "**9-8 suited** — not premium, but suited connectors have great "
                    "potential to make flushes and straights. Limp in."
                ),
            },
            {
                "street": "preflop",
                "action": "call",
                "tip": (
                    "The bot raised! With suited connectors and good implied odds, "
                    "call the raise to see a flop."
                ),
            },
            {
                "street": "flop",
                "action": "call",
                "tip": (
                    "You have a **flush draw** — 9 outs (any spade completes it)! "
                    "Check the Advisor's *Outs* section. With 9 outs, you have ~35% "
                    "chance by the river. The pot odds make this a profitable call."
                ),
            },
            {
                "street": "turn",
                "action": "bet",
                "tip": (
                    "The 7s completed your **flush**! You now have a monster hand. "
                    "Bet for value — make your opponent pay to see the river."
                ),
            },
        ],
        "outro": {
            "title": "Flush Hits — Drawing Pays Off!",
            "body": (
                "You called with a flush draw and hit! The math: 9 outs x 4 "
                "(two cards to come) = ~36% chance. If pot odds give you better than "
                "3:1, calling is profitable long-term.\n\n"
                "**Key concept:** Check the Advisor's *Outs* and *Pot Odds* sections."
            ),
        },
    },

    # ── Hand 5: Continuation Betting ───────────────────────────────
    {
        "title": "The Continuation Bet",
        "intro": {
            "title": "Betting When You Miss",
            "body": (
                "Here's a secret: you don't need the best hand to win a pot! "
                "A **continuation bet** (c-bet) is when you raised preflop and bet "
                "the flop even if you missed.\n\n"
                "It works because your preflop raise signals strength, and the flop "
                "misses most hands. The Advisor shows **Fold Equity** — the chance "
                "your opponent folds."
            ),
        },
        "player_cards": ["As", "Qh"],
        "bot_cards": ["Jc", "Tc"],
        "community": ["8d", "5s", "2h", "Kc", "3d"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            "preflop": [{"action": "call", "amount": 0}],
            "flop": [{"action": "fold", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "raise",
                "tip": "**A-Q** — a strong hand. Raise as the preflop aggressor.",
            },
            {
                "street": "flop",
                "action": "bet",
                "tip": (
                    "The flop missed you completely! But you raised preflop — "
                    "your opponent expects you to have a strong hand. A **c-bet** "
                    "(~½ pot) wins the pot right here most of the time. "
                    "Check the Advisor's *Fold Equity* stat."
                ),
            },
        ],
        "outro": {
            "title": "C-Bet Success!",
            "body": (
                "You won without the best hand! Continuation bets work because your "
                "preflop raise told a story of strength. Your opponent missed too and "
                "couldn't continue.\n\n"
                "**Key concept:** Fold Equity in the Advisor shows the chance your bet wins without showdown."
            ),
        },
    },

    # ── Hand 6: Straight Draw & Outs Math ──────────────────────────
    # dealer=0 (human): pre human first, postflop bot first
    {
        "title": "Straight Draws & Outs Math",
        "intro": {
            "title": "Counting Your Outs",
            "body": (
                "An **open-ended straight draw** (OESD) has 8 outs — cards on either "
                "end that complete your straight.\n\n"
                "**Quick math:** Multiply outs x 2 for one card, x 4 for two cards. "
                "8 outs x 4 = ~32% with flop + turn to come.\n\n"
                "This hand you'll flop a straight draw and hit it on the turn!"
            ),
        },
        "player_cards": ["Jh", "Ts"],
        "bot_cards": ["Ac", "Kh"],
        "community": ["Qc", "9d", "3s", "8h", "2d"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            # pre: human calls SB, bot raises from BB
            "preflop": [{"action": "raise", "amount": 30}],
            # flop: bot acts first — bets 40
            "flop": [{"action": "bet", "amount": 40}],
            # turn: bot acts first — checks, then calls human's bet
            "turn": [{"action": "check", "amount": 0}, {"action": "call", "amount": 0}],
            # river: bot acts first — checks, then calls human's bet
            "river": [{"action": "check", "amount": 0}, {"action": "call", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "call",
                "tip": "**J-T** — great connectors. Limp in to see a flop.",
            },
            {
                "street": "preflop",
                "action": "call",
                "tip": "The bot raised. Call — J-T plays well against a raise with position.",
            },
            {
                "street": "flop",
                "action": "call",
                "tip": (
                    "Q-9 on the board gives you an **open-ended straight draw** "
                    "(any K or 8 makes a straight). That's 8 outs — ~32% by the river. "
                    "Check the Advisor's *Outs* section to see each card listed!"
                ),
            },
            {
                "street": "turn",
                "action": "bet",
                "tip": (
                    "The 8 completed your **straight** (8-9-T-J-Q)! Now bet for value. "
                    "The Advisor's EV section shows the best action and expected profit."
                ),
            },
            {
                "street": "river",
                "action": "bet",
                "tip": (
                    "Your straight is still the best hand. Bet again for value — "
                    "check the Advisor's recommended bet sizing."
                ),
            },
        ],
        "outro": {
            "title": "Straight Completed!",
            "body": (
                "You drew to a straight and got paid! The math:\n"
                "OESD = 8 outs\n"
                "Turn hit chance: 8/47 = ~17%\n"
                "By river: 8 x 4 = ~32%\n\n"
                "**Key concept:** The Advisor's *EV* (Expected Value) shows which action profits most."
            ),
        },
    },

    # ── Hand 7: When to Fold (Range Chart) ─────────────────────────
    # dealer=1 (bot): pre bot first, postflop human first
    {
        "title": "Discipline — When to Fold",
        "intro": {
            "title": "Folding is a Skill",
            "body": (
                "The #1 beginner mistake is playing too many hands. "
                "Knowing **when to fold** saves more money than any bluff.\n\n"
                "This hand you have a **weak hand from early position**. "
                "Open the **Preflop Range Chart** at the bottom of the Advisor — "
                "it shows which hands to play from each position.\n\n"
                "Your hand will be red (fold). Trust the chart!"
            ),
        },
        "player_cards": ["Kd", "5c"],
        "bot_cards": ["As", "Jh"],
        "community": ["Qh", "Td", "7c", "3s", "8d"],
        "dealer_seat": 1,
        "stack_override": 1000,
        "bot_script": {
            "preflop": [{"action": "raise", "amount": 30}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "fold",
                "tip": (
                    "**K-5 offsuit** — looks tempting (it has a King!) but it's a trap. "
                    "Check the Range Chart: this hand is **red** (fold) from most positions. "
                    "The kicker (5) is too weak. Fold and save your chips for a better spot."
                ),
            },
        ],
        "outro": {
            "title": "Smart Fold!",
            "body": (
                "Folding isn't exciting, but it's the foundation of winning poker. "
                "K-5o is dominated by hands like A-K, K-Q, K-J — you'd often be "
                "outkicked and lose a big pot.\n\n"
                "**Key concept:** The Preflop Range Chart (bottom of Advisor) shows "
                "green=raise, yellow=call, red=fold for each position."
            ),
        },
    },

    # ── Hand 8: Bet Sizing for Value ───────────────────────────────
    # dealer=0 (human): pre human first, postflop bot first
    {
        "title": "Bet Sizing",
        "intro": {
            "title": "How Much to Bet",
            "body": (
                "Bet sizing is an art. Too small and you don't get value. "
                "Too big and opponents fold.\n\n"
                "**Value bets** (60-80% pot): Extract chips when you have the best hand.\n"
                "**Half-pot bets** (40-50%): Apply pressure without risking too much.\n\n"
                "This hand you'll flop a **set** (three of a kind with a pocket pair). "
                "Use the bet slider and presets (1/2 Pot, Pot) to size your bets."
            ),
        },
        "player_cards": ["Kh", "Kc"],
        "bot_cards": ["Ac", "Jd"],
        "community": ["Kd", "7c", "3s", "Jh", "5d"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            # pre: human raises, bot calls
            "preflop": [{"action": "call", "amount": 0}],
            # flop: bot acts first — checks, then calls human's bet
            "flop": [{"action": "check", "amount": 0}, {"action": "call", "amount": 0}],
            # turn: bot acts first — checks, then calls human's bet
            "turn": [{"action": "check", "amount": 0}, {"action": "call", "amount": 0}],
            # river: bot acts first — checks, then calls human's bet
            "river": [{"action": "check", "amount": 0}, {"action": "call", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "raise",
                "tip": "**Pocket Kings** — the second-best starting hand! Raise it up.",
            },
            {
                "street": "flop",
                "action": "bet",
                "tip": (
                    "You flopped a **set of Kings** (three Kings)! This is a monster. "
                    "Use the **1/2 Pot** button or drag the slider to ~60% pot for a value bet. "
                    "Too big might scare the opponent away."
                ),
            },
            {
                "street": "turn",
                "action": "bet",
                "tip": (
                    "The bot called — they have something. Keep betting for value. "
                    "Try **2/3 to 3/4 pot** — the Advisor's recommended sizing is shown "
                    "next to each action."
                ),
            },
            {
                "street": "river",
                "action": "bet",
                "tip": (
                    "Final street — last chance to extract value. A solid river bet "
                    "with a set is almost always correct. Check the Advisor's EV numbers."
                ),
            },
        ],
        "outro": {
            "title": "Value Extracted!",
            "body": (
                "You maximized value with proper bet sizing across three streets. "
                "A set is one of the best hands in poker — it's hidden (your opponents "
                "can't see your pocket pair) and very strong.\n\n"
                "**Key concept:** Use the bet slider and 1/2 Pot / Pot presets. "
                "The Advisor shows recommended sizes next to each action."
            ),
        },
    },

    # ── Hand 9: Semi-Bluffing ──────────────────────────────────────
    # dealer=0 (human): pre human first, postflop bot first
    {
        "title": "The Semi-Bluff",
        "intro": {
            "title": "Bluffing with a Safety Net",
            "body": (
                "A **semi-bluff** is a bet with a draw — you want opponents to fold, "
                "but if they call, you still have outs to win.\n\n"
                "It's the best type of bluff because you win in two ways:\n"
                "1. Opponent folds - you win immediately\n"
                "2. Opponent calls - you can still hit your draw\n\n"
                "This hand you'll have a flush draw and use it to semi-bluff!"
            ),
        },
        "player_cards": ["6s", "5s"],
        "bot_cards": ["Ad", "Kc"],
        "community": ["Qs", "Js", "3d", "7s", "Td"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            # pre: human calls SB, bot checks BB option
            "preflop": [{"action": "check", "amount": 0}],
            # flop: bot acts first — checks, then calls human's semi-bluff
            "flop": [{"action": "check", "amount": 0}, {"action": "call", "amount": 0}],
            # turn: bot acts first — checks, then folds to human's value bet
            "turn": [{"action": "check", "amount": 0}, {"action": "fold", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "call",
                "tip": "**6-5 suited** — a speculative hand that plays well in position. Call.",
            },
            {
                "street": "flop",
                "action": "bet",
                "tip": (
                    "You have a **flush draw** (Qs Js on board + your two spades). "
                    "This is a perfect **semi-bluff** spot — bet! If the bot folds, great. "
                    "If they call, you still have 9 outs to make a flush."
                ),
            },
            {
                "street": "turn",
                "action": "bet",
                "tip": (
                    "The 7s completed your **flush**! What started as a semi-bluff "
                    "turned into a real hand. Now bet for value."
                ),
            },
        ],
        "outro": {
            "title": "Semi-Bluff Turned Real!",
            "body": (
                "Semi-bluffing is powerful because it's +EV in two ways. Even if your "
                "flush draw missed, your flop bet had fold equity. When it hits, you "
                "get paid extra because your opponent called the earlier bet.\n\n"
                "**Key concept:** The Advisor's *Fold Equity* + *Outs* together show "
                "why semi-bluffs are profitable."
            ),
        },
    },

    # ── Hand 10: The Grand Finale (All-In Showdown) ────────────────
    # dealer=0 (human): pre human first, postflop bot first
    {
        "title": "All-In Showdown!",
        "intro": {
            "title": "The Final Hand",
            "body": (
                "You've learned the fundamentals — now it's time for the ultimate test.\n\n"
                "This is the moment every poker player dreams of: a **massive pot** "
                "with a **monster hand**. Trust your reads, trust the Advisor, "
                "and go for the win.\n\n"
                "Remember everything you've learned. Good luck!"
            ),
        },
        "player_cards": ["Ah", "As"],
        "bot_cards": ["Ks", "Kd"],
        "community": ["Ad", "Kh", "7c", "2s", "5d"],
        "dealer_seat": 0,
        "stack_override": 1000,
        "bot_script": {
            # pre: human raises SB, bot re-raises from BB
            "preflop": [{"action": "raise", "amount": 40}],
            # flop: bot acts first — bets, then re-raises human's raise
            "flop": [{"action": "bet", "amount": 60}, {"action": "raise", "amount": 200}],
            # turn: bot acts first — bets big
            "turn": [{"action": "bet", "amount": 300}],
            # river: bot acts first — bets all-in
            "river": [{"action": "bet", "amount": 0}],
        },
        "guided": [
            {
                "street": "preflop",
                "action": "raise",
                "tip": (
                    "**Pocket Aces** again — just like Hand 1, but this time the "
                    "bot is fighting back! Raise to build the pot."
                ),
            },
            {
                "street": "preflop",
                "action": "call",
                "tip": (
                    "The bot re-raised! With pocket Aces, call for now — "
                    "you'll trap them on the flop."
                ),
            },
            {
                "street": "flop",
                "action": "raise",
                "tip": (
                    "Ad Kh 7c — you flopped a **set of Aces**! The bot bet — "
                    "they have something strong too. Raise for maximum value!"
                ),
            },
            {
                "street": "flop",
                "action": "call",
                "tip": (
                    "The bot re-raised again! With a set of Aces, you're way ahead. "
                    "Call and let them keep building the pot."
                ),
            },
            {
                "street": "turn",
                "action": "call",
                "tip": (
                    "The bot is betting big! With a set of Aces, you're almost "
                    "certainly ahead. Call — the pot is getting huge."
                ),
            },
            {
                "street": "river",
                "action": "call",
                "tip": (
                    "The bot is going all-in! With **three Aces**, you have an "
                    "incredible hand. This is the moment — **call the all-in!**"
                ),
            },
        ],
        "outro": {
            "title": "You Won the All-In!",
            "body": (
                "**Set of Aces beats set of Kings!** You played the biggest pot "
                "of the tutorial and came out on top.\n\n"
                "You've now learned:\n"
                "Hand strength & equity\n"
                "Position advantage\n"
                "Pot odds & drawing\n"
                "Continuation betting\n"
                "Outs math\n"
                "When to fold\n"
                "Bet sizing\n"
                "Semi-bluffing\n"
                "All-in decisions\n\n"
                "You're ready to play for real. Good luck at the tables!"
            ),
        },
    },
]


# ── Tutorial State Tracker ──────────────────────────────────────────

class TutorialState:
    """Tracks tutorial progress across the 10 scripted hands."""

    def __init__(self):
        self.hand_index: int = 0       # 0-9
        self.is_active: bool = True
        self.is_complete: bool = False
        self.guided_step: int = 0      # which guided action we're on in current hand
        self._bot_action_idx: Dict[str, int] = {}   # per-street bot action index
        self._guided_idx: Dict[str, int] = {}        # per-street guided action index

    def current_hand(self) -> Optional[Dict[str, Any]]:
        if self.hand_index < len(TUTORIAL_HANDS):
            return TUTORIAL_HANDS[self.hand_index]
        return None

    def get_intro(self) -> Optional[Dict[str, str]]:
        hand = self.current_hand()
        return hand["intro"] if hand else None

    def get_outro(self) -> Optional[Dict[str, str]]:
        hand = self.current_hand()
        return hand["outro"] if hand else None

    def get_guided_action(self, street: str) -> Optional[Dict[str, Any]]:
        """Get the next unconsumed guided action for the current street."""
        hand = self.current_hand()
        if not hand:
            return None
        idx = self._guided_idx.get(street, 0)
        count = 0
        for g in hand["guided"]:
            if g["street"] == street:
                if count == idx:
                    return g
                count += 1
        return None

    def consume_guided(self, street: str) -> None:
        """Mark the current guided action for this street as consumed."""
        self._guided_idx[street] = self._guided_idx.get(street, 0) + 1

    def get_bot_action(self, street: str) -> Optional[Dict[str, Any]]:
        """Get the next scripted bot action for the given street."""
        hand = self.current_hand()
        if not hand:
            return None
        idx = self._bot_action_idx.get(street, 0)
        actions = hand.get("bot_script", {}).get(street, [])
        if idx < len(actions):
            return actions[idx]
        return None

    def consume_bot_action(self, street: str) -> None:
        """Advance to the next bot action for this street."""
        self._bot_action_idx[street] = self._bot_action_idx.get(street, 0) + 1

    def advance_hand(self) -> bool:
        """Move to the next hand. Returns True if tutorial is complete."""
        self.hand_index += 1
        self.guided_step = 0
        self._bot_action_idx = {}
        self._guided_idx = {}
        if self.hand_index >= len(TUTORIAL_HANDS):
            self.is_complete = True
            self.is_active = False
            return True
        return False

    def reset_hand_state(self) -> None:
        """Reset action tracking for a new deal of the current hand."""
        self._bot_action_idx = {}
        self._guided_idx = {}

    def to_dict(self) -> Dict[str, Any]:
        hand = self.current_hand()
        return {
            "active": self.is_active,
            "complete": self.is_complete,
            "hand_index": self.hand_index,
            "total_hands": len(TUTORIAL_HANDS),
            "title": hand["title"] if hand else None,
        }
